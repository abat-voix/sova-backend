from django.contrib import admin

from sova.core.admin import AbstractBaseModelAdmin, AbstractHistoryModelAdmin
from sova.processes.models import (
    ActionAttachment,
    ActionInstance,
    ActionResult,
    StageInstance,
    WorkflowInstance,
)


@admin.register(ActionAttachment)
class ActionAttachmentAdmin(AbstractHistoryModelAdmin[ActionAttachment]):
    """Админка вложений действий. Запись журнала — не редактируется."""

    list_display = ("id", "file", "action_instance", "uploaded_by", "uploaded_at")
    list_display_links = ("file",)
    list_select_related = ("action_instance", "uploaded_by")
    search_fields = ("id", "file")
    autocomplete_fields = ("action_instance", "uploaded_by")


@admin.register(ActionInstance)
class ActionInstanceAdmin(AbstractBaseModelAdmin[ActionInstance]):
    """Админка экземпляров действий workflow."""

    list_display = (
        "id",
        "action_name_snapshot",
        "status",
        "stage_instance",
        "action",
        "responsible",
        "planned_start",
    )
    list_display_links = ("action_name_snapshot",)
    list_select_related = ("stage_instance", "action", "responsible")
    search_fields = ("id", "action_name_snapshot", "status")
    list_filter = ("status",)
    autocomplete_fields = ("stage_instance", "action", "responsible")


@admin.register(ActionResult)
class ActionResultAdmin(AbstractHistoryModelAdmin[ActionResult]):
    """Админка результатов действий. Запись журнала — не редактируется."""

    list_display = (
        "id",
        "outcome_name_snapshot",
        "action_instance",
        "outcome",
        "created_by",
        "created_at",
    )
    list_display_links = ("outcome_name_snapshot",)
    list_select_related = ("action_instance", "outcome", "created_by")
    search_fields = ("id", "outcome_name_snapshot", "comment")
    autocomplete_fields = ("action_instance", "outcome", "created_by")


@admin.register(StageInstance)
class StageInstanceAdmin(AbstractBaseModelAdmin[StageInstance]):
    """Админка экземпляров этапов workflow."""

    list_display = ("id", "workflow_instance", "stage", "status", "context_type", "added_at")
    list_select_related = ("workflow_instance", "stage")
    search_fields = ("id", "status")
    list_filter = ("context_type", "status")
    autocomplete_fields = ("workflow_instance", "stage", "added_by")


@admin.register(WorkflowInstance)
class WorkflowInstanceAdmin(AbstractBaseModelAdmin[WorkflowInstance]):
    """Админка процессов workflow."""

    list_display = ("id", "workflow", "interaction", "status", "started_at")
    list_select_related = ("workflow", "interaction")
    search_fields = ("id", "status")
    list_filter = ("status",)
    autocomplete_fields = ("workflow", "interaction", "created_by")
