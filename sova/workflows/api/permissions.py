from __future__ import annotations

from typing import Any

from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission, IsAuthenticated

from accounts.models import SystemRole
from accounts.services import get_system_role


EDITABLE_ROLES = frozenset({SystemRole.HEAD, SystemRole.PLATFORM_ADMIN})


def can_manage_workflows(user) -> bool:
    """Whether the user may access the workflow administration API."""
    return bool(
        user
        and user.is_authenticated
        and get_system_role(user) in EDITABLE_ROLES
    )


def can_edit_workflow(user, workflow) -> bool:
    """Whether the user may mutate a particular workflow and its children."""
    role = get_system_role(user)
    return role == SystemRole.PLATFORM_ADMIN or (
        role == SystemRole.HEAD and workflow.created_by_id == user.pk
    )


def workflow_for_object(obj: Any):
    """Resolve the owning workflow for a workflow or one of its child models."""
    if obj.__class__.__name__ == "Workflow":
        return obj
    if hasattr(obj, "workflow_id"):
        return obj.workflow
    if hasattr(obj, "stage_id"):
        return obj.stage.workflow
    if hasattr(obj, "action_id"):
        return obj.action.stage.workflow
    if hasattr(obj, "from_stage_id"):
        return obj.from_stage.workflow
    if hasattr(obj, "outcome_id"):
        return obj.outcome.action.stage.workflow
    if hasattr(obj, "target_action_id"):
        return obj.target_action.stage.workflow
    if hasattr(obj, "depends_on_action_id"):
        return obj.depends_on_action.stage.workflow
    raise TypeError(f"Cannot resolve workflow for {type(obj)!r}")


class CanManageWorkflows(IsAuthenticated):
    """Allow only heads and platform administrators into workflow APIs."""

    message = "Управление workflow доступно руководителю и администратору платформы."

    def has_permission(self, request, view) -> bool:
        return super().has_permission(request, view) and can_manage_workflows(
            request.user
        )

    def has_object_permission(self, request, view, obj) -> bool:
        if request.method in ("GET", "HEAD", "OPTIONS") or getattr(
            view, "action", None
        ) == "validate_definition":
            return True
        return can_edit_workflow(request.user, workflow_for_object(obj))


class WorkflowOwnershipMixin:
    """Apply ownership checks to create operations with nested workflow FKs."""

    def _assert_can_edit_workflow(self, workflow) -> None:
        if not can_edit_workflow(self.request.user, workflow):
            raise PermissionDenied(
                "Руководитель может изменять только созданные им workflow."
            )

    def _assert_create_ownership(self, serializer) -> None:
        data = serializer.validated_data
        if "workflow" in data:
            workflow = data["workflow"]
        elif "stage" in data:
            workflow = data["stage"].workflow
        elif "action" in data:
            workflow = data["action"].stage.workflow
        elif "from_stage" in data:
            workflow = data["from_stage"].workflow
        elif "outcome" in data:
            workflow = data["outcome"].action.stage.workflow
        elif "depends_on_action" in data:
            workflow = data["depends_on_action"].stage.workflow
        else:
            raise TypeError("Cannot resolve workflow from validated data")
        self._assert_can_edit_workflow(workflow)

    def perform_create(self, serializer) -> None:
        self._assert_create_ownership(serializer)
        super().perform_create(serializer)
