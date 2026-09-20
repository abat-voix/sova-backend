from rest_framework import status
from rest_framework.test import APITestCase

from sova.core.tests.base import BaseApiTestMixin
from sova.core.tests.factories import UserFactory
from sova.core.tests.media import TemporaryMediaMixin
from sova.processes.models import ActionInstance, ActionResult
from sova.processes.tests.factories import (
    ActionAttachmentFactory,
    ActionInstanceFactory,
    ActionResultFactory,
)
from sova.workflows.tests.factories import ActionOutcomeFactory


class ActionResultApiTestCase(TemporaryMediaMixin, BaseApiTestMixin, APITestCase):
    """Тесты чтения и фиксации результатов /api/processes/action-results/."""

    url_basename = "processes:action-result"
    model = ActionResult
    allow_update = False
    allow_delete = False

    def create_instance(self, **kwargs) -> ActionResult:
        """Создаёт результат действия."""
        return ActionResultFactory(**kwargs)

    def get_expected_data(self, instance: ActionResult) -> dict:
        """Поля read-представления результата."""
        return {
            "id": str(instance.pk),
            "action_instance": str(instance.action_instance_id),
            "outcome": {
                "id": str(instance.outcome_id),
                "code": instance.outcome.code,
                "name": instance.outcome.name,
            },
            "outcome_name_snapshot": instance.outcome_name_snapshot,
            "comment": instance.comment,
        }

    def get_post_data(self) -> dict:
        """Данные создания: исход из действия экземпляра."""
        action_instance = ActionInstanceFactory()
        outcome = ActionOutcomeFactory(action=action_instance.action)
        return {
            "action_instance": str(action_instance.pk),
            "outcome": str(outcome.pk),
            "comment": "Договорились о встрече",
        }

    def get_change_data(self) -> dict:
        """Обновление не поддерживается."""
        return {}

    def build_data(self, outcome_kwargs: dict | None = None) -> dict:
        """Данные создания с исходом, настроенным через `outcome_kwargs`."""
        action_instance = ActionInstanceFactory()
        outcome = ActionOutcomeFactory(
            action=action_instance.action,
            **(outcome_kwargs or {}),
        )
        return {"action_instance": str(action_instance.pk), "outcome": str(outcome.pk)}

    def test_add_fills_snapshot_and_created_by(self) -> None:
        """Слепок названия исхода и автор берутся из данных, а не из запроса."""
        data = self.build_data()
        data["outcome_name_snapshot"] = "Подмена"

        response = self.client.post(path=self.list_url, data=data, format="json")

        # Проверяем слепок названия исхода
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.data)
        result = ActionResult.objects.get(pk=response.data["id"])
        self.assertEqual(result.outcome_name_snapshot, result.outcome.name)
        # Проверяем автора
        self.assertEqual(response.data["created_by"]["id"], self.user.pk)

    def test_add_returns_400_for_outcome_of_another_action(self) -> None:
        """Исход другого действия отклоняется."""
        data = self.build_data()
        data["outcome"] = str(ActionOutcomeFactory().pk)

        response = self.client.post(path=self.list_url, data=data, format="json")

        # Проверяем, что ошибка привязана к полю outcome
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("outcome", response.data)

    def test_add_returns_400_for_inactive_outcome(self) -> None:
        """Неактивный исход отклоняется."""
        data = self.build_data(outcome_kwargs={"active": False})

        response = self.client.post(path=self.list_url, data=data, format="json")

        # Проверяем, что ошибка привязана к полю outcome
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("outcome", response.data)

    def test_add_returns_400_without_required_comment(self) -> None:
        """Исход с comment_required требует непустой комментарий."""
        data = self.build_data(outcome_kwargs={"comment_required": True})

        without = self.client.post(path=self.list_url, data=data, format="json")
        blank = self.client.post(
            path=self.list_url,
            data={**data, "comment": "   "},
            format="json",
        )
        with_comment = self.client.post(
            path=self.list_url,
            data={**data, "comment": "Причина отказа"},
            format="json",
        )

        # Проверяем, что комментарий из пробелов не считается заполненным
        self.assertEqual(without.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("comment", without.data)
        self.assertEqual(blank.status_code, status.HTTP_400_BAD_REQUEST)
        # Проверяем, что с комментарием результат фиксируется
        self.assertEqual(with_comment.status_code, status.HTTP_201_CREATED, msg=with_comment.data)

    def test_add_requires_attachment_when_outcome_demands_it(self) -> None:
        """Исход с attachment_required требует хотя бы одно вложение к действию."""
        data = self.build_data(outcome_kwargs={"attachment_required": True})

        without = self.client.post(path=self.list_url, data=data, format="json")
        ActionAttachmentFactory(
            action_instance=ActionInstance.objects.get(pk=data["action_instance"]),
        )
        with_attachment = self.client.post(path=self.list_url, data=data, format="json")

        # Проверяем, что без вложения результат отклонён
        self.assertEqual(without.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("outcome", without.data)
        # Проверяем, что после загрузки вложения результат фиксируется
        self.assertEqual(
            with_attachment.status_code,
            status.HTTP_201_CREATED,
            msg=with_attachment.data,
        )

    def test_add_returns_400_when_result_already_recorded(self) -> None:
        """Повторный результат для действия отклоняется (OneToOne)."""
        existing = ActionResultFactory()
        other_outcome = ActionOutcomeFactory(action=existing.action_instance.action)

        response = self.client.post(
            path=self.list_url,
            data={
                "action_instance": str(existing.action_instance_id),
                "outcome": str(other_outcome.pk),
            },
            format="json",
        )

        # Проверяем, что журнал не перезаписывается
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("action_instance", response.data)

    def test_filters_select_matching_results(self) -> None:
        """Фильтры экземпляра действия, исхода и автора выбирают нужные результаты."""
        author = UserFactory()
        target = ActionResultFactory(created_by=author)
        ActionResultFactory()

        def ids(params: dict) -> list[str]:
            response = self.client.get(path=self.list_url, data=params)
            return [item["id"] for item in response.data["results"]]

        # Проверяем каждый фильтр
        self.assertEqual(
            ids({"action_instance__ids": str(target.action_instance_id)}),
            [str(target.pk)],
        )
        self.assertEqual(ids({"outcome__ids": str(target.outcome_id)}), [str(target.pk)])
        self.assertEqual(ids({"created_by__ids": str(author.pk)}), [str(target.pk)])
