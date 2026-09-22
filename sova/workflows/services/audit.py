from django.contrib.auth.models import AbstractBaseUser
from django.db.models import Model

from sova.workflows.enum import WorkflowChangeType
from sova.workflows.models import (
    ActionDependency,
    ActionFeature,
    ActionOutcome,
    ActionTransition,
    StageTransition,
    Workflow,
    WorkflowAction,
    WorkflowChange,
    WorkflowStage,
)


class WorkflowAuditService:
    """
    Аудит изменений определения workflow — запись в WorkflowChange.

    Любая сущность структуры (этап, действие, исход, переход, зависимость)
    относится к workflow через цепочку внешних ключей; цепочки описаны в
    `_WORKFLOW_PATHS`. Запись при удалении нужно делать до самого удаления,
    пока цепочка ещё читается.
    """

    _WORKFLOW_PATHS: dict[type[Model], tuple[str, ...]] = {
        Workflow: (),
        WorkflowStage: ("workflow",),
        WorkflowAction: ("stage", "workflow"),
        ActionOutcome: ("action", "stage", "workflow"),
        ActionTransition: ("outcome", "action", "stage", "workflow"),
        ActionDependency: ("action", "stage", "workflow"),
        ActionFeature: ("action", "stage", "workflow"),
        StageTransition: ("from_stage", "workflow"),
    }

    def record(
        self,
        instance: Model,
        change_type: WorkflowChangeType,
        changed_by: AbstractBaseUser | None,
    ) -> WorkflowChange | None:
        """
        Записывает изменение сущности workflow в аудит.

        Удаление самого Workflow не журналируется: записи аудита связаны с ним
        каскадом и исчезли бы вместе с ним.
        """
        if isinstance(instance, Workflow) and change_type == WorkflowChangeType.DELETED:
            return None

        return WorkflowChange.objects.create(
            change_type=change_type,
            entity_type=instance._meta.model_name,
            entity_id=instance.pk,
            workflow=self._resolve_workflow(instance=instance),
            created_by=changed_by,
        )

    def _resolve_workflow(self, instance: Model) -> Workflow:
        """Проходит по цепочке связей сущности до её workflow."""
        current = instance
        for attribute in self._WORKFLOW_PATHS[type(instance)]:
            current = getattr(current, attribute)
        return current


workflow_audit_service = WorkflowAuditService()
