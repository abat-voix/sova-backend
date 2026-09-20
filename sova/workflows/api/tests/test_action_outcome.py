from rest_framework import status
from rest_framework.test import APITestCase

from sova.core.tests.base import BaseApiTestMixin
from sova.workflows.models import ActionOutcome
from sova.workflows.tests.factories import ActionOutcomeFactory, WorkflowActionFactory


class ActionOutcomeApiTestCase(BaseApiTestMixin, APITestCase):
    """Тесты CRUD /api/workflows/action-outcomes/."""

    url_basename = "workflows:action-outcome"
    model = ActionOutcome

    def create_instance(self, **kwargs) -> ActionOutcome:
        """Создаёт исход действия."""
        return ActionOutcomeFactory(**kwargs)

    def get_expected_data(self, instance: ActionOutcome) -> dict:
        """Поля read-представления исхода."""
        return {
            "id": str(instance.pk),
            "code": instance.code,
            "name": instance.name,
            "active": instance.active,
            "comment_required": instance.comment_required,
            "attachment_required": instance.attachment_required,
            "action": {"id": str(instance.action_id), "name": instance.action.name},
        }

    def get_post_data(self) -> dict:
        """Данные создания исхода (действие — по id)."""
        return {
            "code": "agreed",
            "name": "Согласовано",
            "comment_required": True,
            "action": str(WorkflowActionFactory().pk),
        }

    def get_change_data(self) -> dict:
        """Данные обновления исхода."""
        return {"name": "Отказ", "attachment_required": True}

    def get_search_term(self, instance: ActionOutcome) -> str:
        """Поиск по названию."""
        return instance.name

    def test_add_returns_400_with_duplicate_code(self) -> None:
        """Повтор кода исхода в действии возвращает 400."""
        existing = ActionOutcomeFactory(code="ok")

        response = self.client.post(
            path=self.list_url,
            data={"code": "ok", "name": "Дубль", "action": str(existing.action_id)},
            format="json",
        )

        # Проверяем, что нарушение unique_action_outcome_code отдано как 400
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_filter_by_action_ids(self) -> None:
        """Фильтр action__ids возвращает исходы указанных действий."""
        target = ActionOutcomeFactory()
        ActionOutcomeFactory()

        response = self.client.get(
            path=self.list_url,
            data={"action__ids": str(target.action_id)},
        )

        # Проверяем, что найден только исход выбранного действия
        self.assertEqual(
            [item["id"] for item in response.data["results"]],
            [str(target.pk)],
        )
