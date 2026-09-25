from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Supervision, SystemRole, UserRole
from sova.core.tests.factories import UserFactory
from sova.interactions.services import responsible_service
from sova.interactions.tests.factories import InteractionFactory
from sova.processes.models import ActionRollback
from sova.processes.tests.factories import (
    ActionInstanceFactory,
    ActionResultFactory,
    StageInstanceFactory,
    StageRollbackFactory,
    WorkflowInstanceFactory,
)
from sova.workflows.tests.factories import WorkflowFactory


class ProcessVisibilityApiTestCase(APITestCase):
    """Процессы, этапы, результаты и откаты видны только по видимым взаимодействиям."""

    def setUp(self) -> None:
        """Руководитель и процесс на взаимодействии КАМа чужой команды."""
        self.head = self.create_user(SystemRole.HEAD)
        other_head = self.create_user(SystemRole.HEAD)
        foreign_kam = self.create_user(SystemRole.KAM)
        Supervision.objects.create(kam=foreign_kam, head=other_head)
        self.foreign = InteractionFactory()
        responsible_service.assign(interaction=self.foreign, manager=foreign_kam, assigned_by=None)
        self.own = InteractionFactory()
        responsible_service.assign(interaction=self.own, manager=self.head, assigned_by=None)

        self.foreign_process = WorkflowInstanceFactory(interaction=self.foreign)
        self.foreign_stage = StageInstanceFactory(workflow_instance=self.foreign_process)
        foreign_action = ActionInstanceFactory(stage_instance=self.foreign_stage)
        self.foreign_result = ActionResultFactory(action_instance=foreign_action)
        self.foreign_stage_rollback = StageRollbackFactory(workflow_instance=self.foreign_process)
        self.foreign_action_rollback = ActionRollback.objects.create(
            workflow_instance=self.foreign_process,
            stage_instance=self.foreign_stage,
            from_action_instance=foreign_action,
            to_action_instance=foreign_action,
            reason="Откат",
        )
        self.own_process = WorkflowInstanceFactory(interaction=self.own)
        self.client.force_authenticate(user=self.head)

    @staticmethod
    def create_user(role: str):
        """Пользователь с ролью СОВА."""
        user = UserFactory()
        UserRole.objects.create(user=user, role=role)
        return user

    def list_ids(self, basename: str) -> set[str]:
        """Идентификаторы из списка эндпоинта процессов."""
        response = self.client.get(reverse(f"processes:{basename}-list"), {"page_size": 100})
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=basename)
        return {item["id"] for item in response.data["results"]}

    def test_foreign_process_is_hidden(self) -> None:
        """Процесс чужой команды не виден в списке и по id, свой — виден."""
        ids = self.list_ids("workflow-instance")

        # Проверяем список и доску
        self.assertIn(str(self.own_process.pk), ids)
        self.assertNotIn(str(self.foreign_process.pk), ids)
        board = self.client.get(reverse("processes:workflow-instance-board", args=[self.foreign_process.pk]))
        self.assertEqual(board.status_code, status.HTTP_404_NOT_FOUND)

    def test_foreign_stages_results_and_rollbacks_are_hidden(self) -> None:
        """Этапы, результаты и откаты процесса чужой команды не видны."""
        # Проверяем каждый журнал
        self.assertNotIn(str(self.foreign_stage.pk), self.list_ids("stage-instance"))
        self.assertNotIn(str(self.foreign_result.pk), self.list_ids("action-result"))
        self.assertNotIn(str(self.foreign_stage_rollback.pk), self.list_ids("stage-rollback"))
        self.assertNotIn(str(self.foreign_action_rollback.pk), self.list_ids("action-rollback"))

    def test_cannot_cancel_foreign_stage(self) -> None:
        """Отменить этап процесса чужой команды нельзя — 404."""
        response = self.client.post(
            reverse("processes:stage-instance-cancel", args=[self.foreign_stage.pk]),
            {"mode": "return", "reason": "Причина"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_cannot_start_process_on_foreign_interaction(self) -> None:
        """Запустить процесс на взаимодействии чужой команды нельзя — 400 на поле interaction."""
        response = self.client.post(
            reverse("processes:workflow-instance-list"),
            {"workflow": str(WorkflowFactory().pk), "interaction": str(self.foreign.pk)},
            format="json",
        )

        # Проверяем ошибку поля
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("interaction", response.data)
