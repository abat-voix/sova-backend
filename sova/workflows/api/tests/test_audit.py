from rest_framework.test import APITestCase

from sova.core.tests.factories import UserFactory
from sova.workflows.enum import WorkflowChangeType
from sova.workflows.models import Workflow, WorkflowChange
from sova.workflows.tests.factories import (
    ActionDependencyFactory,
    ActionOutcomeFactory,
    ActionTransitionFactory,
    StageTransitionFactory,
    WorkflowActionFactory,
    WorkflowFactory,
    WorkflowStageFactory,
)


class WorkflowAuditTestCase(APITestCase):
    """Тесты записи в аудит WorkflowChange при правке структуры workflow через API."""

    def setUp(self) -> None:
        """Аутентифицирует клиента и создаёт workflow с этапом."""
        self.user = UserFactory()
        self.client.force_authenticate(user=self.user)
        self.workflow = WorkflowFactory()
        self.stage = WorkflowStageFactory(workflow=self.workflow)

    def assert_single_change(
        self,
        change_type: str,
        entity_type: str,
        entity_id: str,
        workflow=None,
    ) -> None:
        """Проверяет, что записана ровно одна запись аудита с ожидаемыми полями."""
        changes = WorkflowChange.objects.filter(entity_id=entity_id)

        # Проверяем, что запись ровно одна
        self.assertEqual(changes.count(), 1)
        change = changes.get()
        # Проверяем тип изменения и сущности
        self.assertEqual(change.change_type, change_type)
        self.assertEqual(change.entity_type, entity_type)
        # Проверяем workflow и автора
        self.assertEqual(change.workflow_id, (workflow or self.workflow).pk)
        self.assertEqual(change.created_by_id, self.user.pk)

    def test_create_workflow_records_change(self) -> None:
        """Создание workflow пишет запись created."""
        response = self.client.post(
            path="/api/workflows/workflows/",
            data={"name": "Новый", "code": "new"},
            format="json",
        )

        self.assert_single_change(
            change_type=WorkflowChangeType.CREATED,
            entity_type="workflow",
            entity_id=response.data["id"],
            workflow=Workflow.objects.get(pk=response.data["id"]),
        )

    def test_create_stage_records_change(self) -> None:
        """Создание этапа пишет запись created для его workflow."""
        response = self.client.post(
            path="/api/workflows/workflow-stages/",
            data={
                "name": "Новый этап",
                "sort_order": 100,
                "workflow": str(self.workflow.pk),
            },
            format="json",
        )

        self.assert_single_change(
            change_type=WorkflowChangeType.CREATED,
            entity_type="workflowstage",
            entity_id=response.data["id"],
        )

    def test_update_stage_records_change(self) -> None:
        """Изменение этапа пишет запись updated."""
        self.client.patch(
            path=f"/api/workflows/workflow-stages/{self.stage.pk}/",
            data={"name": "Переименован"},
            format="json",
        )

        self.assert_single_change(
            change_type=WorkflowChangeType.UPDATED,
            entity_type="workflowstage",
            entity_id=self.stage.pk,
        )

    def test_delete_action_records_change_before_removal(self) -> None:
        """Удаление действия пишет запись deleted и не теряет id удалённой сущности."""
        action = WorkflowActionFactory(stage=self.stage)
        action_id = action.pk

        self.client.delete(path=f"/api/workflows/workflow-actions/{action_id}/")

        self.assert_single_change(
            change_type=WorkflowChangeType.DELETED,
            entity_type="workflowaction",
            entity_id=action_id,
        )

    def test_nested_entities_resolve_their_workflow(self) -> None:
        """Исход, переход и зависимость относятся к workflow через цепочку связей."""
        outcome = ActionOutcomeFactory(action=WorkflowActionFactory(stage=self.stage))
        transition = ActionTransitionFactory(outcome=outcome)
        dependency = ActionDependencyFactory(
            action=WorkflowActionFactory(stage=self.stage),
            depends_on_action=WorkflowActionFactory(stage=self.stage),
        )

        self.client.patch(
            path=f"/api/workflows/action-outcomes/{outcome.pk}/",
            data={"name": "Изменён"},
            format="json",
        )
        self.client.patch(
            path=f"/api/workflows/action-transitions/{transition.pk}/",
            data={"active": False},
            format="json",
        )
        self.client.patch(
            path=f"/api/workflows/action-dependencies/{dependency.pk}/",
            data={"active": False},
            format="json",
        )

        # Проверяем, что все три изменения привязаны к одному workflow
        self.assertEqual(
            WorkflowChange.objects.filter(workflow=self.workflow).count(),
            3,
        )

    def test_failed_validation_records_nothing(self) -> None:
        """Отклонённый запрос не пишет в аудит."""
        self.client.post(
            path="/api/workflows/workflow-stages/",
            data={"name": "Без порядка", "workflow": str(self.workflow.pk)},
            format="json",
        )

        # Проверяем, что аудит пуст
        self.assertFalse(WorkflowChange.objects.exists())

    def test_delete_workflow_succeeds_without_orphan_audit(self) -> None:
        """Удаление самого workflow проходит: его аудит уходит каскадом вместе с ним."""
        response = self.client.delete(
            path=f"/api/workflows/workflows/{self.workflow.pk}/",
        )

        # Проверяем успешное удаление и отсутствие записей аудита
        self.assertEqual(response.status_code, 204)
        self.assertFalse(WorkflowChange.objects.exists())


    def test_create_stage_transition_records_change(self) -> None:
        """Создание связи между этапами пишет запись created для её workflow."""
        target = WorkflowStageFactory(workflow=self.workflow)

        response = self.client.post(
            path="/api/workflows/stage-transitions/",
            data={"from_stage": str(self.stage.pk), "to_stage": str(target.pk)},
            format="json",
        )

        self.assert_single_change(
            change_type=WorkflowChangeType.CREATED,
            entity_type="stagetransition",
            entity_id=response.data["id"],
        )

    def test_update_stage_transition_records_change(self) -> None:
        """Изменение связи между этапами пишет запись updated."""
        transition = StageTransitionFactory(from_stage=self.stage)

        self.client.patch(
            path=f"/api/workflows/stage-transitions/{transition.pk}/",
            data={"active": False},
            format="json",
        )

        self.assert_single_change(
            change_type=WorkflowChangeType.UPDATED,
            entity_type="stagetransition",
            entity_id=transition.pk,
        )

    def test_delete_stage_transition_records_change_before_removal(self) -> None:
        """Удаление связи между этапами пишет запись deleted и не теряет id."""
        transition = StageTransitionFactory(from_stage=self.stage)
        transition_id = transition.pk

        self.client.delete(path=f"/api/workflows/stage-transitions/{transition_id}/")

        self.assert_single_change(
            change_type=WorkflowChangeType.DELETED,
            entity_type="stagetransition",
            entity_id=transition_id,
        )
