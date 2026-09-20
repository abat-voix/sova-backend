from datetime import datetime, timezone

from rest_framework import status
from rest_framework.test import APITestCase

from sova.core.tests.base import BaseApiTestMixin
from sova.interactions.tests.factories import InteractionFactory
from sova.processes.enum import StageInstanceContextType
from sova.processes.models import StageInstance
from sova.processes.tests.factories import StageInstanceFactory, WorkflowInstanceFactory
from sova.workflows.tests.factories import WorkflowStageFactory


class StageInstanceApiTestCase(BaseApiTestMixin, APITestCase):
    """Тесты чтения и создания /api/processes/stage-instances/."""

    url_basename = "processes:stage-instance"
    model = StageInstance
    allow_update = False
    allow_delete = False

    def create_instance(self, **kwargs) -> StageInstance:
        """Создаёт экземпляр этапа."""
        return StageInstanceFactory(**kwargs)

    def get_expected_data(self, instance: StageInstance) -> dict:
        """Поля read-представления экземпляра этапа."""
        return {
            "id": str(instance.pk),
            "context_type": instance.context_type,
            "context_id": instance.context_id and str(instance.context_id),
            "status": instance.status,
            "completed_at": None,
            "workflow_instance": str(instance.workflow_instance_id),
            "stage": {
                "id": str(instance.stage_id),
                "name": instance.stage.name,
                "workflow": str(instance.stage.workflow_id),
            },
        }

    def get_post_data(self) -> dict:
        """Данные создания: этап из workflow процесса, контекст — взаимодействие."""
        process = WorkflowInstanceFactory()
        stage = WorkflowStageFactory(workflow=process.workflow)
        return {
            "status": "in_progress",
            "context_type": StageInstanceContextType.INTERACTION,
            "context_id": str(process.interaction_id),
            "workflow_instance": str(process.pk),
            "stage": str(stage.pk),
        }

    def get_change_data(self) -> dict:
        """Обновление не поддерживается."""
        return {}

    def test_add_sets_added_by(self) -> None:
        """Создание проставляет автора из запроса."""
        response = self.client.post(
            path=self.list_url,
            data=self.get_post_data(),
            format="json",
        )

        # Проверяем автора
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.data)
        self.assertEqual(response.data["added_by"]["id"], self.user.pk)

    def test_add_returns_400_for_stage_from_another_workflow(self) -> None:
        """Этап другого workflow отклоняется."""
        process = WorkflowInstanceFactory()

        response = self.client.post(
            path=self.list_url,
            data={
                "status": "in_progress",
                "workflow_instance": str(process.pk),
                "stage": str(WorkflowStageFactory().pk),
            },
            format="json",
        )

        # Проверяем, что ошибка привязана к полю stage
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("stage", response.data)

    def test_add_returns_400_for_context_of_another_interaction(self) -> None:
        """Контекст другого взаимодействия отклоняется (StageInstance.clean)."""
        data = self.get_post_data()
        data["context_id"] = str(InteractionFactory().pk)

        response = self.client.post(path=self.list_url, data=data, format="json")

        # Проверяем, что ошибка привязана к context_id
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("context_id", response.data)

    def test_add_returns_400_for_unknown_product_context(self) -> None:
        """Несуществующий контекст продукта отклоняется."""
        data = self.get_post_data()
        data["context_type"] = StageInstanceContextType.IT_PRODUCT
        data["context_id"] = "00000000-0000-0000-0000-000000000000"

        response = self.client.post(path=self.list_url, data=data, format="json")

        # Проверяем, что clean() отрабатывает и для полиморфного контекста
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("context_id", response.data)

    def assert_filter_returns(self, params: dict, expected: list[StageInstance]) -> None:
        """Проверяет, что список с фильтром содержит ровно ожидаемые экземпляры."""
        response = self.client.get(path=self.list_url, data=params)

        # Проверяем состав выдачи (порядок не важен)
        self.assertEqual(
            sorted(item["id"] for item in response.data["results"]),
            sorted(str(instance.pk) for instance in expected),
        )

    def test_filters_select_matching_stage_instances(self) -> None:
        """Фильтры процесса, взаимодействия, этапа, контекста и статуса выбирают нужное."""
        target = StageInstanceFactory(
            status="done",
            context_type=StageInstanceContextType.INTERACTION,
            context_id=None,
        )
        StageInstanceFactory()

        self.assert_filter_returns(
            {"workflow_instance__ids": str(target.workflow_instance_id)},
            [target],
        )
        self.assert_filter_returns(
            {"interaction__ids": str(target.workflow_instance.interaction_id)},
            [target],
        )
        self.assert_filter_returns({"stage__ids": str(target.stage_id)}, [target])
        self.assert_filter_returns({"status": "done"}, [target])

    def test_filter_by_context_type_and_id(self) -> None:
        """Фильтры context_type и context_id находят экземпляры этапа по контексту."""
        process = WorkflowInstanceFactory()
        target = StageInstanceFactory(
            workflow_instance=process,
            context_type=StageInstanceContextType.INTERACTION,
            context_id=process.interaction_id,
        )
        StageInstanceFactory()

        self.assert_filter_returns(
            {
                "context_type": StageInstanceContextType.INTERACTION,
                "context_id": str(process.interaction_id),
            },
            [target],
        )

    def test_filter_is_completed(self) -> None:
        """Фильтр is_completed отделяет завершённые этапы от активных."""
        active = StageInstanceFactory()
        done = StageInstanceFactory(completed_at=datetime.now(tz=timezone.utc))

        self.assert_filter_returns({"is_completed": "true"}, [done])
        self.assert_filter_returns({"is_completed": "false"}, [active])
