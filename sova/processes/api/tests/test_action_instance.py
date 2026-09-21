import uuid

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from sova.core.tests.base import BaseApiTestMixin
from sova.core.tests.factories import UserFactory
from sova.processes.enum import StageInstanceStatus, WorkflowInstanceStatus
from sova.processes.models import ActionInstance, ActionResult
from sova.processes.tests.base import COMPLETED, EngineApiTestCase
from sova.processes.tests.factories import ActionAttachmentFactory, ActionInstanceFactory
from sova.workflows.models import ActionOutcome


class ActionInstanceApiTestCase(BaseApiTestMixin, APITestCase):
    """Тесты чтения /api/processes/action-instances/: состояние действий меняет только движок."""

    url_basename = "processes:action-instance"
    model = ActionInstance
    allow_create = False
    allow_update = False
    allow_delete = False

    def create_instance(self, **kwargs) -> ActionInstance:
        """Создаёт экземпляр действия."""
        return ActionInstanceFactory(**kwargs)

    def get_expected_data(self, instance: ActionInstance) -> dict:
        """Поля read-представления экземпляра действия."""
        return {
            "id": str(instance.pk),
            "action_name_snapshot": instance.action_name_snapshot,
            "status": instance.status,
            "execution_no": instance.execution_no,
            "triggered_at": None,
            "stage_instance": str(instance.stage_instance_id),
            "action": {"id": str(instance.action_id), "name": instance.action.name},
            "responsible": None,
        }

    def get_post_data(self) -> dict:
        """Создание не поддерживается."""
        return {}

    def get_change_data(self) -> dict:
        """Обновление не поддерживается."""
        return {}

    def assert_filter_returns(self, params: dict, expected: list[ActionInstance]) -> None:
        """Проверяет, что список с фильтром содержит ровно ожидаемые экземпляры."""
        response = self.client.get(path=self.list_url, data=params)

        # Проверяем состав выдачи (порядок не важен)
        self.assertEqual(
            sorted(item["id"] for item in response.data["results"]),
            sorted(str(instance.pk) for instance in expected),
        )

    def test_filters_select_matching_action_instances(self) -> None:
        """Фильтры этапа, процесса, действия, ответственного и статуса выбирают нужное."""
        manager = UserFactory()
        target = ActionInstanceFactory(status="completed", responsible=manager)
        ActionInstanceFactory()

        self.assert_filter_returns(
            {"stage_instance__ids": str(target.stage_instance_id)},
            [target],
        )
        self.assert_filter_returns(
            {"workflow_instance__ids": str(target.stage_instance.workflow_instance_id)},
            [target],
        )
        self.assert_filter_returns({"action__ids": str(target.action_id)}, [target])
        self.assert_filter_returns({"responsible__ids": str(manager.pk)}, [target])
        self.assert_filter_returns({"status": "completed"}, [target])


class CompleteActionApiTestCase(EngineApiTestCase):
    """Тесты POST /api/processes/action-instances/{id}/complete/: завершение действия движком."""

    def setUp(self) -> None:
        """Два этапа: в первом действие, после его завершения открывается второе."""
        super().setUp()
        self.first = self.builder.stage("Первый")
        self.second = self.builder.stage("Второй", after=(self.first,))
        self.find = self.builder.action(self.first, "Найти контакт")
        self.meet = self.builder.action(self.second, "Организовать встречу")
        self.process = self.start()

    def url(self, action, context=None) -> str:
        """URL завершения последнего исполнения действия."""
        instance = self.action_instance(self.process, action, context)
        return reverse("processes:action-instance-complete", args=[instance.pk])

    def post(self, action, **data):
        """Завершает действие; исход по умолчанию — «Выполнено»."""
        data.setdefault("outcome", str(ActionOutcome.objects.get(action=action, code="done").pk))
        return self.client.post(path=self.url(action), data=data, format="json")

    def test_complete_returns_what_changed_in_the_process(self) -> None:
        """Ответ описывает результат и всё, что изменилось: закрытые и открытые этапы, запущенные действия."""
        response = self.post(self.find, comment="Нашли")

        first_instance = self.stage_instance(self.process, self.first)
        second_instance = self.stage_instance(self.process, self.second)
        # Проверяем успешный ответ и завершённое действие
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
        self.assertEqual(response.data["action_instance"]["status"], COMPLETED)
        # Проверяем результат
        self.assertEqual(response.data["result"]["comment"], "Нашли")
        self.assertEqual(response.data["result"]["outcome_name_snapshot"], "Выполнено")
        self.assertEqual(response.data["result"]["created_by"]["id"], self.user.pk)
        # Проверяем закрытые и открытые этапы и запущенные действия
        self.assertEqual([item["id"] for item in response.data["completed_stages"]], [str(first_instance.pk)])
        self.assertEqual([item["id"] for item in response.data["opened_stages"]], [str(second_instance.pk)])
        self.assertEqual(
            [item["id"] for item in response.data["activated_actions"]],
            [str(self.action_instance(self.process, self.meet).pk)],
        )
        self.assertFalse(response.data["is_workflow_completed"])

    def test_complete_without_comment_records_empty_comment(self) -> None:
        """Комментарий необязателен: без него сохраняется пустой."""
        response = self.post(self.find)

        # Проверяем результат
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
        self.assertEqual(ActionResult.objects.get().comment, "")

    def test_complete_last_action_completes_the_process(self) -> None:
        """Завершение последнего обязательного действия завершает процесс."""
        self.post(self.find)

        response = self.post(self.meet)

        self.process.refresh_from_db()
        # Проверяем признак в ответе и статус процесса
        self.assertTrue(response.data["is_workflow_completed"])
        self.assertEqual(self.process.status, WorkflowInstanceStatus.COMPLETED)
        self.assertEqual(self.stage_status(self.process, self.second), StageInstanceStatus.COMPLETED)

    def test_complete_returns_409_for_action_that_is_not_in_progress(self) -> None:
        """Ожидающее действие завершить нельзя: 409 и код invalid_state."""
        response = self.post(self.meet)

        # Проверяем статус и код
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "invalid_state")

    def test_complete_returns_409_for_already_completed_action(self) -> None:
        """Повторное завершение того же исполнения возвращает 409."""
        self.post(self.find)

        response = self.client.post(
            path=reverse(
                "processes:action-instance-complete",
                args=[self.action_instance(self.process, self.find).pk],
            ),
            data={"outcome": str(ActionOutcome.objects.get(action=self.find, code="done").pk)},
            format="json",
        )

        # Проверяем статус и код
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "invalid_state")
        self.assertEqual(ActionResult.objects.count(), 1)

    def test_complete_returns_400_for_outcome_of_another_action(self) -> None:
        """Исход другого действия: 400 и код outcome_mismatch."""
        response = self.post(self.find, outcome=str(ActionOutcome.objects.get(action=self.meet, code="done").pk))

        # Проверяем статус и код
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "outcome_mismatch")

    def test_complete_returns_400_for_inactive_outcome(self) -> None:
        """Неактивный исход: 400 и код outcome_inactive."""
        outcome = self.builder.outcome(self.find, "obsolete", is_active=False)

        response = self.post(self.find, outcome=str(outcome.pk))

        # Проверяем статус и код
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "outcome_inactive")

    def test_complete_returns_400_without_required_comment(self) -> None:
        """Исход с обязательным комментарием без него: 400 и код is_comment_required, действие не завершено."""
        outcome = self.builder.outcome(self.find, "agreed", is_comment_required=True)

        response = self.post(self.find, outcome=str(outcome.pk), comment="   ")

        # Проверяем статус, код и то, что состояние не изменилось
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "is_comment_required")
        self.assertFalse(ActionResult.objects.exists())

    def test_complete_requires_attachment_when_outcome_demands_it(self) -> None:
        """Исход с обязательным вложением: без файла 400 и код is_attachment_required, с файлом 200."""
        outcome = self.builder.outcome(self.find, "signed", is_attachment_required=True)

        without = self.post(self.find, outcome=str(outcome.pk))
        ActionAttachmentFactory(action_instance=self.action_instance(self.process, self.find))
        with_file = self.post(self.find, outcome=str(outcome.pk))

        # Проверяем оба ответа
        self.assertEqual(without.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(without.data["code"], "is_attachment_required")
        self.assertEqual(with_file.status_code, status.HTTP_200_OK, msg=with_file.data)

    def test_complete_returns_400_when_outcome_is_missing_or_unknown(self) -> None:
        """Без исхода и с несуществующим исходом: 400 и ошибка по полю outcome."""
        url = self.url(self.find)

        missing = self.client.post(path=url, data={}, format="json")
        unknown = self.client.post(path=url, data={"outcome": str(uuid.uuid4())}, format="json")

        # Проверяем ошибки полей
        self.assertEqual(missing.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("outcome", missing.data)
        self.assertEqual(unknown.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("outcome", unknown.data)

    def test_complete_returns_404_for_unknown_action_instance(self) -> None:
        """Несуществующее исполнение действия: 404."""
        response = self.client.post(
            path=reverse("processes:action-instance-complete", args=[uuid.uuid4()]),
            data={"outcome": str(uuid.uuid4())},
            format="json",
        )

        # Проверяем статус
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_complete_requires_authentication(self) -> None:
        """Анонимный запрос отклоняется."""
        self.client.force_authenticate(user=None)

        response = self.post(self.find)

        # Проверяем, что доступ запрещён
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))
