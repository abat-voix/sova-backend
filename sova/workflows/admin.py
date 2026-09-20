from django.contrib import admin

from sova.core.admin import AbstractBaseModelAdmin, AbstractHistoryModelAdmin
from sova.workflows.models import (
    ActionDependency,
    ActionOutcome,
    ActionTransition,
    Workflow,
    WorkflowAction,
    WorkflowChange,
    WorkflowStage,
)


@admin.register(ActionDependency)
class ActionDependencyAdmin(AbstractBaseModelAdmin[ActionDependency]):
    """Админка зависимостей действий workflow."""

    list_display = ("id", "action", "depends_on_action", "active", "created_at")
    list_select_related = ("action", "depends_on_action")
    search_fields = ("id",)
    list_filter = ("active",)
    autocomplete_fields = ("action", "depends_on_action")


@admin.register(ActionOutcome)
class ActionOutcomeAdmin(AbstractBaseModelAdmin[ActionOutcome]):
    """Админка исходов действий workflow."""

    list_display = ("id", "name", "code", "action", "active", "created_at")
    list_display_links = ("name",)
    list_select_related = ("action",)
    search_fields = ("id", "name", "code")
    list_filter = ("active", "comment_required", "attachment_required")
    autocomplete_fields = ("action",)


@admin.register(ActionTransition)
class ActionTransitionAdmin(AbstractBaseModelAdmin[ActionTransition]):
    """Админка переходов между действиями workflow."""

    list_display = ("id", "outcome", "target_action", "active", "created_at")
    list_select_related = ("outcome", "target_action")
    search_fields = ("id",)
    list_filter = ("active",)
    autocomplete_fields = ("outcome", "target_action")


@admin.register(Workflow)
class WorkflowAdmin(AbstractBaseModelAdmin[Workflow]):
    """Админка шаблонов workflow."""

    list_display = ("id", "name", "code", "audience", "is_base", "active", "created_at")
    list_display_links = ("name",)
    search_fields = ("id", "name", "code")
    list_filter = ("audience", "is_base", "active")
    autocomplete_fields = ("created_by",)


@admin.register(WorkflowAction)
class WorkflowActionAdmin(AbstractBaseModelAdmin[WorkflowAction]):
    """Админка действий workflow."""

    list_display = ("id", "name", "stage", "sort_order", "active", "created_at")
    list_display_links = ("name",)
    list_select_related = ("stage",)
    search_fields = ("id", "name")
    list_filter = ("active", "is_optional")
    autocomplete_fields = ("stage",)


@admin.register(WorkflowChange)
class WorkflowChangeAdmin(AbstractHistoryModelAdmin[WorkflowChange]):
    """Админка аудита изменений workflow. Запись журнала — не редактируется."""

    list_display = ("id", "workflow", "change_type", "entity_type", "created_by", "created_at")
    list_select_related = ("workflow", "created_by")
    search_fields = ("id", "change_type", "entity_type")
    list_filter = ("change_type", "entity_type")
    autocomplete_fields = ("workflow", "created_by")


@admin.register(WorkflowStage)
class WorkflowStageAdmin(AbstractBaseModelAdmin[WorkflowStage]):
    """Админка этапов workflow."""

    list_display = ("id", "name", "workflow", "sort_order", "active", "created_at")
    list_display_links = ("name",)
    list_select_related = ("workflow",)
    search_fields = ("id", "name", "type")
    list_filter = ("is_initial", "is_final", "is_optional", "active")
    autocomplete_fields = ("workflow",)
