from rest_framework.test import APITestCase

from accounts.models import SystemRole, UserRole
from sova.core.tests.base import BaseApiTestMixin
from sova.core.tests.factories import UserFactory
from sova.processes.models import StageRollback
from sova.processes.tests.factories import StageRollbackFactory


class StageRollbackApiTestCase(BaseApiTestMixin, APITestCase):
    """Тесты чтения /api/processes/stage-rollbacks/: журнал откатов пишет только движок."""

    url_basename = "processes:stage-rollback"
    model = StageRollback
    allow_create = False
    allow_update = False
    allow_delete = False

    def setUp(self) -> None:
        """Администратор платформы: процессы видны только по видимым взаимодействиям."""
        super().setUp()
        UserRole.objects.create(user=self.user, role=SystemRole.PLATFORM_ADMIN)

    def create_instance(self, **kwargs) -> StageRollback:
        """Создаёт запись журнала откатов."""
        return StageRollbackFactory(**kwargs)

    def stage_data(self, stage_instance) -> dict:
        """Краткое представление экземпляра этапа в записи журнала."""
        return {
            "id": str(stage_instance.pk),
            "stage": {
                "id": str(stage_instance.stage_id),
                "name": stage_instance.stage.name,
                "workflow": str(stage_instance.stage.workflow_id),
            },
            "context_type": stage_instance.context_type,
            "context_id": stage_instance.context_id and str(stage_instance.context_id),
        }

    def get_expected_data(self, instance: StageRollback) -> dict:
        """Поля read-представления записи журнала."""
        return {
            "id": str(instance.pk),
            "workflow_instance": str(instance.workflow_instance_id),
            "from_stage_instance": self.stage_data(instance.from_stage_instance),
            "to_stage_instance": self.stage_data(instance.to_stage_instance),
            "reason": instance.reason,
            "mode": instance.mode,
            "created_by": None,
        }

    def get_post_data(self) -> dict:
        """Создание не поддерживается."""
        return {}

    def get_change_data(self) -> dict:
        """Обновление не поддерживается."""
        return {}

    def get_search_term(self, instance: StageRollback) -> str:
        """Поиск по причине."""
        return instance.reason

    def test_filters_select_matching_records(self) -> None:
        """Фильтры процесса, автора и режима выбирают нужные записи."""
        author = UserFactory()
        target = StageRollbackFactory(created_by=author, mode="last_only")
        StageRollbackFactory()

        def ids(params: dict) -> list[str]:
            response = self.client.get(path=self.list_url, data=params)
            return [item["id"] for item in response.data["results"]]

        # Проверяем каждый фильтр
        self.assertEqual(ids({"workflow_instance__ids": str(target.workflow_instance_id)}), [str(target.pk)])
        self.assertEqual(ids({"created_by__ids": str(author.pk)}), [str(target.pk)])
        self.assertEqual(ids({"mode": "last_only"}), [str(target.pk)])
