from rest_framework import status
from rest_framework.test import APITestCase

from sova.core.tests.base import BaseApiTestMixin
from sova.workflows.models import WorkflowStage
from sova.workflows.tests.factories import WorkflowFactory, WorkflowStageFactory


class WorkflowStageApiTestCase(BaseApiTestMixin, APITestCase):
    """Тесты CRUD /api/workflows/workflow-stages/."""

    url_basename = "workflows:workflow-stage"
    model = WorkflowStage

    def create_instance(self, **kwargs) -> WorkflowStage:
        """Создаёт этап workflow."""
        return WorkflowStageFactory(**kwargs)

    def get_expected_data(self, instance: WorkflowStage) -> dict:
        """Поля read-представления этапа."""
        return {
            "id": str(instance.pk),
            "name": instance.name,
            "type": instance.type,
            "description": instance.description,
            "sort_order": instance.sort_order,
            "is_initial": instance.is_initial,
            "is_final": instance.is_final,
            "is_optional": instance.is_optional,
            "active": instance.active,
            "workflow": {
                "id": str(instance.workflow_id),
                "name": instance.workflow.name,
                "code": instance.workflow.code,
            },
        }

    def get_post_data(self) -> dict:
        """Данные создания этапа (workflow — по id)."""
        return {
            "name": "Поиск контактов",
            "sort_order": 1,
            "workflow": str(WorkflowFactory().pk),
        }

    def get_change_data(self) -> dict:
        """Данные обновления этапа."""
        return {"name": "Коммуникация", "is_optional": True}

    def get_search_term(self, instance: WorkflowStage) -> str:
        """Поиск по названию."""
        return instance.name

    def test_add_returns_400_with_duplicate_sort_order(self) -> None:
        """Повтор порядкового номера в workflow возвращает 400."""
        existing = WorkflowStageFactory(sort_order=5)

        response = self.client.post(
            path=self.list_url,
            data={
                "name": "Дубль порядка",
                "sort_order": 5,
                "workflow": str(existing.workflow_id),
            },
            format="json",
        )

        # Проверяем, что нарушение unique_workflow_stage_order отдано как 400
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_add_second_initial_stage_returns_400(self) -> None:
        """Второй начальный этап в workflow отклоняется с 400."""
        existing = WorkflowStageFactory(is_initial=True)

        response = self.client.post(
            path=self.list_url,
            data={
                "name": "Ещё начальный",
                "sort_order": 99,
                "is_initial": True,
                "workflow": str(existing.workflow_id),
            },
            format="json",
        )

        # Проверяем, что условное ограничение ловится валидацией
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("is_initial", response.data)

    def test_add_initial_stage_in_another_workflow_creates_stage(self) -> None:
        """Начальные этапы разных workflow сосуществуют."""
        WorkflowStageFactory(is_initial=True)

        response = self.client.post(
            path=self.list_url,
            data={
                "name": "Начальный в другом",
                "sort_order": 1,
                "is_initial": True,
                "workflow": str(WorkflowFactory().pk),
            },
            format="json",
        )

        # Проверяем, что ограничение действует только в рамках одного workflow
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.data)

    def test_change_initial_stage_keeps_flag(self) -> None:
        """Обновление самого начального этапа не конфликтует с его же флагом."""
        initial = WorkflowStageFactory(is_initial=True)

        response = self.client.patch(
            path=self.detail_url(initial),
            data={"name": "Новое имя", "is_initial": True},
            format="json",
        )

        # Проверяем, что собственный флаг is_initial не считается конфликтом
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)

    def test_filter_by_workflow_ids_and_flags(self) -> None:
        """Фильтры workflow__ids, is_initial, is_final выбирают нужные этапы."""
        workflow = WorkflowFactory()
        first = WorkflowStageFactory(workflow=workflow, is_initial=True)
        last = WorkflowStageFactory(workflow=workflow, is_final=True)
        WorkflowStageFactory()

        def ids(params: dict) -> list[str]:
            response = self.client.get(path=self.list_url, data=params)
            return sorted(item["id"] for item in response.data["results"])

        # Проверяем фильтр по workflow
        self.assertEqual(
            ids({"workflow__ids": str(workflow.pk)}),
            sorted([str(first.pk), str(last.pk)]),
        )
        # Проверяем фильтры по признакам
        self.assertEqual(ids({"is_initial": "true"}), [str(first.pk)])
        self.assertEqual(ids({"is_final": "true"}), [str(last.pk)])
