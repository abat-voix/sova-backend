from django.contrib import admin

from sova.core.admin import AbstractBaseModelAdmin, AbstractHistoryModelAdmin
from sova.workflows.models import (
    ActionDependency,
    ActionOutcome,
    ActionFeature,
    ActionTransition,
    StageTransition,
    Workflow,
    WorkflowAction,
    WorkflowChange,
    WorkflowStage,
)


class ActionFeatureInline(admin.TabularInline):
    model = ActionFeature
    extra = 0
    fields = ("code", "sort_order", "is_active", "settings")


@admin.register(ActionDependency)
class ActionDependencyAdmin(AbstractBaseModelAdmin[ActionDependency]):
    """Админка зависимостей действий workflow."""

    list_display = ("id", "action", "depends_on_action", "is_active", "created_at")
    list_select_related = ("action", "depends_on_action")
    search_fields = ("id",)
    list_filter = ("is_active",)
    autocomplete_fields = ("action", "depends_on_action")


@admin.register(ActionOutcome)
class ActionOutcomeAdmin(AbstractBaseModelAdmin[ActionOutcome]):
    """Админка исходов действий workflow."""

    list_display = ("id", "name", "code", "action", "is_active", "created_at")
    list_display_links = ("name",)
    list_select_related = ("action",)
    search_fields = ("id", "name", "code")
    list_filter = ("is_active", "is_comment_required", "is_attachment_required")
    autocomplete_fields = ("action",)


@admin.register(ActionTransition)
class ActionTransitionAdmin(AbstractBaseModelAdmin[ActionTransition]):
    """Админка переходов между действиями workflow."""

    list_display = ("id", "outcome", "target_action", "is_active", "created_at")
    list_select_related = ("outcome", "target_action")
    search_fields = ("id",)
    list_filter = ("is_active",)
    autocomplete_fields = ("outcome", "target_action")


@admin.register(StageTransition)
class StageTransitionAdmin(AbstractBaseModelAdmin[StageTransition]):
    """Админка связей между этапами workflow."""

    list_display = ("id", "from_stage", "to_stage", "is_active", "created_at")
    list_select_related = ("from_stage", "to_stage")
    search_fields = ("id",)
    list_filter = ("is_active",)
    autocomplete_fields = ("from_stage", "to_stage")


@admin.register(Workflow)
class WorkflowAdmin(AbstractBaseModelAdmin[Workflow]):
    """Админка шаблонов workflow."""

    list_display = ("id", "name", "code", "audience", "is_base", "is_active", "created_at")
    list_display_links = ("name",)
    search_fields = ("id", "name", "code")
    list_filter = ("audience", "is_base", "is_active")
    autocomplete_fields = ("created_by",)


@admin.register(WorkflowAction)
class WorkflowActionAdmin(AbstractBaseModelAdmin[WorkflowAction]):
    """Админка действий workflow."""

    list_display = ("id", "name", "stage", "sort_order", "is_active", "created_at")
    list_display_links = ("name",)
    list_select_related = ("stage",)
    search_fields = ("id", "name")
    list_filter = ("is_active", "is_optional")
    autocomplete_fields = ("stage",)
    inlines = (ActionFeatureInline,)


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

    list_display = ("id", "name", "workflow", "sort_order", "is_active", "created_at")
    list_display_links = ("name",)
    list_select_related = ("workflow",)
    search_fields = ("id", "name", "description")
    list_filter = ("is_initial", "is_final", "is_optional", "is_active")
    autocomplete_fields = ("workflow",)
