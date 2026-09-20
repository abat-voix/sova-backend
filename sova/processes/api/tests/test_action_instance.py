from datetime import datetime, timedelta, timezone

from rest_framework import status
from rest_framework.test import APITestCase

from sova.core.tests.base import BaseApiTestMixin
from sova.core.tests.factories import UserFactory
from sova.processes.models import ActionInstance
from sova.processes.tests.factories import ActionInstanceFactory, StageInstanceFactory
from sova.workflows.models import WorkflowAction
from sova.workflows.tests.factories import WorkflowActionFactory


class ActionInstanceApiTestCase(BaseApiTestMixin, APITestCase):
    """Тесты чтения и создания /api/processes/action-instances/."""

    url_basename = "processes:action-instance"
    model = ActionInstance
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
            "stage_instance": str(instance.stage_instance_id),
            "action": {"id": str(instance.action_id), "name": instance.action.name},
            "responsible": None,
        }

    def get_post_data(self) -> dict:
        """Данные создания: действие из этапа экземпляра этапа."""
        stage_instance = StageInstanceFactory()
        action = WorkflowActionFactory(stage=stage_instance.stage)
        return {
            "status": "in_progress",
            "stage_instance": str(stage_instance.pk),
            "action": str(action.pk),
        }

    def get_change_data(self) -> dict:
        """Обновление не поддерживается."""
        return {}

    def test_add_fills_name_snapshot_from_action(self) -> None:
        """Слепок названия берётся из действия, а не из запроса."""
        data = self.get_post_data()
        data["action_name_snapshot"] = "Подмена"

        response = self.client.post(path=self.list_url, data=data, format="json")

        # Проверяем, что слепок равен названию действия на момент создания
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.data)
        action = WorkflowAction.objects.get(pk=data["action"])
        self.assertEqual(response.data["action_name_snapshot"], action.name)

    def test_add_computes_planned_end_from_default_duration(self) -> None:
        """planned_end вычисляется как planned_start + default_duration_days."""
        data = self.get_post_data()
        action = WorkflowAction.objects.get(pk=data["action"])
        action.default_duration_days = 5
        action.save()
        start = datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc)
        data["planned_start"] = start.isoformat()

        response = self.client.post(path=self.list_url, data=data, format="json")

        # Проверяем вычисленное плановое окончание
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.data)
        instance = ActionInstance.objects.get(pk=response.data["id"])
        self.assertEqual(instance.planned_end, start + timedelta(days=5))

    def test_add_keeps_explicit_planned_end(self) -> None:
        """Явно переданный planned_end не перезаписывается расчётом."""
        data = self.get_post_data()
        action = WorkflowAction.objects.get(pk=data["action"])
        action.default_duration_days = 5
        action.save()
        start = datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc)
        end = start + timedelta(days=1)
        data.update({"planned_start": start.isoformat(), "planned_end": end.isoformat()})

        response = self.client.post(path=self.list_url, data=data, format="json")

        # Проверяем, что сохранено переданное значение
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.data)
        self.assertEqual(ActionInstance.objects.get(pk=response.data["id"]).planned_end, end)

    def test_add_returns_400_for_action_from_another_stage(self) -> None:
        """Действие, не принадлежащее этапу экземпляра этапа, отклоняется."""
        data = self.get_post_data()
        data["action"] = str(WorkflowActionFactory().pk)

        response = self.client.post(path=self.list_url, data=data, format="json")

        # Проверяем, что ошибка привязана к полю action
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("action", response.data)

    def test_add_returns_400_when_planned_end_before_start(self) -> None:
        """Плановое окончание раньше планового начала отклоняется."""
        data = self.get_post_data()
        data.update(
            {
                "planned_start": "2026-03-10T09:00:00Z",
                "planned_end": "2026-03-01T09:00:00Z",
            },
        )

        response = self.client.post(path=self.list_url, data=data, format="json")

        # Проверяем, что ошибка привязана к planned_end
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("planned_end", response.data)

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
        target = ActionInstanceFactory(status="done", responsible=manager)
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
        self.assert_filter_returns({"status": "done"}, [target])
