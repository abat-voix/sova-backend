from datetime import datetime, timedelta, timezone

from rest_framework.test import APITestCase

from sova.core.tests.base import BaseApiTestMixin
from sova.core.tests.factories import UserFactory
from sova.workflows.models import WorkflowChange
from sova.workflows.tests.factories import WorkflowChangeFactory, WorkflowFactory


class WorkflowChangeApiTestCase(BaseApiTestMixin, APITestCase):
    """Тесты чтения аудита /api/workflows/workflow-changes/."""

    url_basename = "workflows:workflow-change"
    model = WorkflowChange
    allow_create = False
    allow_update = False
    allow_delete = False

    def create_instance(self, **kwargs) -> WorkflowChange:
        """Создаёт запись аудита."""
        return WorkflowChangeFactory(**kwargs)

    def get_expected_data(self, instance: WorkflowChange) -> dict:
        """Поля read-представления записи аудита."""
        return {
            "id": str(instance.pk),
            "change_type": instance.change_type,
            "entity_type": instance.entity_type,
            "entity_id": str(instance.entity_id),
            "workflow": str(instance.workflow_id),
            "created_by": None,
        }

    def assert_filter_returns(self, params: dict, expected: list[WorkflowChange]) -> None:
        """Проверяет, что список с фильтром содержит ровно ожидаемые записи."""
        response = self.client.get(path=self.list_url, data=params)

        # Проверяем состав выдачи (порядок не важен)
        self.assertEqual(
            sorted(item["id"] for item in response.data["results"]),
            sorted(str(change.pk) for change in expected),
        )

    def test_filters_select_matching_records(self) -> None:
        """Фильтры workflow__ids, change_type, entity_type, created_by__ids работают."""
        workflow = WorkflowFactory()
        author = UserFactory()
        target = WorkflowChangeFactory(
            workflow=workflow,
            change_type="deleted",
            entity_type="workflowaction",
            created_by=author,
        )
        WorkflowChangeFactory()

        self.assert_filter_returns({"workflow__ids": str(workflow.pk)}, [target])
        self.assert_filter_returns({"change_type": "deleted"}, [target])
        self.assert_filter_returns({"entity_type": "workflowaction"}, [target])
        self.assert_filter_returns({"created_by__ids": str(author.pk)}, [target])
        self.assert_filter_returns({"entity_id": str(target.entity_id)}, [target])

    def test_filter_by_created_period(self) -> None:
        """Фильтры created_at__gte/created_at__lte ограничивают период по дате."""
        now = datetime.now(tz=timezone.utc)
        old = WorkflowChangeFactory()
        recent = WorkflowChangeFactory()
        WorkflowChange.objects.filter(pk=old.pk).update(created_at=now - timedelta(days=40))
        date_from = (now - timedelta(days=10)).date().isoformat()

        self.assert_filter_returns({"created_at__gte": date_from}, [recent])
        self.assert_filter_returns({"created_at__lte": date_from}, [old])
