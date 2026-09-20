from rest_framework import status
from rest_framework.test import APITestCase

from sova.core.tests.base import BaseApiTestMixin
from sova.workflows.models import WorkflowAction
from sova.workflows.tests.factories import (
    WorkflowActionFactory,
    WorkflowFactory,
    WorkflowStageFactory,
)


class WorkflowActionApiTestCase(BaseApiTestMixin, APITestCase):
    """Тесты CRUD /api/workflows/workflow-actions/."""

    url_basename = "workflows:workflow-action"
    model = WorkflowAction

    def create_instance(self, **kwargs) -> WorkflowAction:
        """Создаёт действие workflow."""
        return WorkflowActionFactory(**kwargs)

    def get_expected_data(self, instance: WorkflowAction) -> dict:
        """Поля read-представления действия."""
        return {
            "id": str(instance.pk),
            "name": instance.name,
            "description": instance.description,
            "sort_order": instance.sort_order,
            "default_duration_days": instance.default_duration_days,
            "is_optional": instance.is_optional,
            "active": instance.active,
            "stage": {
                "id": str(instance.stage_id),
                "name": instance.stage.name,
                "workflow": str(instance.stage.workflow_id),
            },
        }

    def get_post_data(self) -> dict:
        """Данные создания действия (этап — по id)."""
        return {
            "name": "Позвонить в приёмную",
            "sort_order": 1,
            "default_duration_days": 3,
            "stage": str(WorkflowStageFactory().pk),
        }

    def get_change_data(self) -> dict:
        """Данные обновления действия."""
        return {"name": "Написать письмо", "default_duration_days": 5}

    def get_search_term(self, instance: WorkflowAction) -> str:
        """Поиск по названию."""
        return instance.name

    def test_add_returns_400_with_duplicate_sort_order(self) -> None:
        """Повтор порядкового номера в этапе возвращает 400."""
        existing = WorkflowActionFactory(sort_order=7)

        response = self.client.post(
            path=self.list_url,
            data={
                "name": "Дубль порядка",
                "sort_order": 7,
                "stage": str(existing.stage_id),
            },
            format="json",
        )

        # Проверяем, что нарушение unique_stage_action_order отдано как 400
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_filter_by_stage_and_workflow_ids(self) -> None:
        """Фильтры stage__ids и workflow__ids выбирают действия этапа/workflow."""
        workflow = WorkflowFactory()
        stage = WorkflowStageFactory(workflow=workflow)
        in_stage = WorkflowActionFactory(stage=stage)
        in_workflow = WorkflowActionFactory(
            stage=WorkflowStageFactory(workflow=workflow),
        )
        WorkflowActionFactory()

        def ids(params: dict) -> list[str]:
            response = self.client.get(path=self.list_url, data=params)
            return sorted(item["id"] for item in response.data["results"])

        # Проверяем фильтр по этапу
        self.assertEqual(ids({"stage__ids": str(stage.pk)}), [str(in_stage.pk)])
        # Проверяем фильтр по workflow через этап
        self.assertEqual(
            ids({"workflow__ids": str(workflow.pk)}),
            sorted([str(in_stage.pk), str(in_workflow.pk)]),
        )
