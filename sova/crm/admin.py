from django.contrib import admin

from sova.crm.admin_base import AbstractBaseModelAdmin, AbstractHistoryModelAdmin
from sova.crm.models import (
    ActionAttachment,
    ActionDependency,
    ActionInstance,
    ActionOutcome,
    ActionResult,
    ActionTransition,
    B2CClient,
    Contact,
    ContactPerson,
    Contract,
    ITDirection,
    ITProduct,
    ITProgram,
    License,
    Responsible,
    StageInstance,
    University,
    Vendor,
    Workflow,
    WorkflowAction,
    WorkflowChange,
    WorkflowInstance,
    WorkflowStage,
)


@admin.register(ActionAttachment)
class ActionAttachmentAdmin(AbstractHistoryModelAdmin[ActionAttachment]):
    """Админка вложений действий. Запись журнала — не редактируется."""

    list_display = ("id", "file", "action_instance", "uploaded_by", "uploaded_at")
    list_display_links = ("file",)
    list_select_related = ("action_instance", "uploaded_by")
    search_fields = ("id", "file")
    autocomplete_fields = ("action_instance", "uploaded_by")


@admin.register(ActionDependency)
class ActionDependencyAdmin(AbstractBaseModelAdmin[ActionDependency]):
    """Админка зависимостей действий workflow."""

    list_display = ("id", "action", "depends_on_action", "active", "created_at")
    list_select_related = ("action", "depends_on_action")
    search_fields = ("id",)
    list_filter = ("active",)
    autocomplete_fields = ("action", "depends_on_action")


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


@admin.register(ActionOutcome)
class ActionOutcomeAdmin(AbstractBaseModelAdmin[ActionOutcome]):
    """Админка исходов действий workflow."""

    list_display = ("id", "name", "code", "action", "active", "created_at")
    list_display_links = ("name",)
    list_select_related = ("action",)
    search_fields = ("id", "name", "code")
    list_filter = ("active", "comment_required", "attachment_required")
    autocomplete_fields = ("action",)


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


@admin.register(ActionTransition)
class ActionTransitionAdmin(AbstractBaseModelAdmin[ActionTransition]):
    """Админка переходов между действиями workflow."""

    list_display = ("id", "outcome", "target_action", "active", "created_at")
    list_select_related = ("outcome", "target_action")
    search_fields = ("id",)
    list_filter = ("active",)
    autocomplete_fields = ("outcome", "target_action")


@admin.register(B2CClient)
class B2CClientAdmin(AbstractBaseModelAdmin[B2CClient]):
    """Админка B2C-клиентов."""

    list_display = ("id", "full_name", "kind", "phone", "is_active", "created_at")
    list_display_links = ("full_name",)
    search_fields = ("id", "full_name", "inn", "email", "phone")
    list_filter = ("kind", "is_active")


@admin.register(Contact)
class ContactAdmin(AbstractBaseModelAdmin[Contact]):
    """Админка сделок."""

    list_display = ("id", "university", "b2c_client", "is_active", "created_at")
    list_select_related = ("university", "b2c_client")
    search_fields = ("id", "comment", "university__name", "b2c_client__full_name")
    list_filter = ("is_active",)
    autocomplete_fields = ("university", "b2c_client")


@admin.register(ContactPerson)
class ContactPersonAdmin(AbstractBaseModelAdmin[ContactPerson]):
    """Админка контактных лиц."""

    list_display = (
        "id",
        "full_name",
        "position",
        "university",
        "b2c_client",
        "is_active",
        "created_at",
    )
    list_display_links = ("full_name",)
    list_select_related = ("university", "b2c_client")
    search_fields = ("id", "full_name", "email", "phone")
    list_filter = ("is_active",)
    autocomplete_fields = ("university", "b2c_client")


@admin.register(Contract)
class ContractAdmin(AbstractBaseModelAdmin[Contract]):
    """Админка договоров."""

    list_display = ("id", "contract_number", "contact", "signed_at", "created_at")
    list_display_links = ("contract_number",)
    list_select_related = ("contact",)
    search_fields = ("id", "contract_number")
    autocomplete_fields = ("contact",)


@admin.register(ITDirection)
class ITDirectionAdmin(AbstractBaseModelAdmin[ITDirection]):
    """Админка ИТ-направлений."""

    list_display = ("id", "name", "external_code", "is_active", "created_at")
    list_display_links = ("name",)
    search_fields = ("id", "name", "external_code")
    list_filter = ("is_active",)


@admin.register(ITProduct)
class ITProductAdmin(AbstractBaseModelAdmin[ITProduct]):
    """Админка ИТ-продуктов."""

    list_display = ("id", "name", "vendor", "is_active", "created_at")
    list_display_links = ("name",)
    list_select_related = ("vendor",)
    search_fields = ("id", "name", "external_code")
    list_filter = ("is_active",)
    autocomplete_fields = ("vendor", "programs")


@admin.register(ITProgram)
class ITProgramAdmin(AbstractBaseModelAdmin[ITProgram]):
    """Админка ИТ-программ."""

    list_display = ("id", "name", "it_direction", "is_active", "created_at")
    list_display_links = ("name",)
    list_select_related = ("it_direction",)
    search_fields = ("id", "name")
    list_filter = ("is_active",)
    autocomplete_fields = ("it_direction",)


@admin.register(License)
class LicenseAdmin(AbstractBaseModelAdmin[License]):
    """Админка лицензий."""

    list_display = ("id", "contract", "it_product", "is_signed", "is_active", "created_at")
    list_select_related = ("contract", "it_product")
    search_fields = ("id",)
    list_filter = ("is_signed", "is_active")
    autocomplete_fields = ("contract", "it_product", "created_by")


@admin.register(Responsible)
class ResponsibleAdmin(AbstractBaseModelAdmin[Responsible]):
    """Админка назначений ответственных на сделку."""

    list_display = ("id", "contact", "manager", "assigned_by", "assigned_at")
    list_select_related = ("contact", "manager", "assigned_by")
    search_fields = ("id",)
    autocomplete_fields = ("contact", "manager", "assigned_by")


@admin.register(StageInstance)
class StageInstanceAdmin(AbstractBaseModelAdmin[StageInstance]):
    """Админка экземпляров этапов workflow."""

    list_display = ("id", "workflow_instance", "stage", "status", "context_type", "added_at")
    list_select_related = ("workflow_instance", "stage")
    search_fields = ("id", "status")
    list_filter = ("context_type", "status")
    autocomplete_fields = ("workflow_instance", "stage", "added_by")


@admin.register(University)
class UniversityAdmin(AbstractBaseModelAdmin[University]):
    """Админка вузов."""

    list_display = ("id", "name", "inn", "is_active", "created_at")
    list_display_links = ("name",)
    search_fields = ("id", "name", "inn", "external_code")
    list_filter = ("is_active",)


@admin.register(Vendor)
class VendorAdmin(AbstractBaseModelAdmin[Vendor]):
    """Админка вендоров."""

    list_display = ("id", "name", "external_code", "is_active", "created_at")
    list_display_links = ("name",)
    search_fields = ("id", "name", "external_code")
    list_filter = ("is_active",)


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


@admin.register(WorkflowInstance)
class WorkflowInstanceAdmin(AbstractBaseModelAdmin[WorkflowInstance]):
    """Админка процессов workflow."""

    list_display = ("id", "workflow", "contact", "status", "started_at")
    list_select_related = ("workflow", "contact")
    search_fields = ("id", "status")
    list_filter = ("status",)
    autocomplete_fields = ("workflow", "contact", "created_by")


@admin.register(WorkflowStage)
class WorkflowStageAdmin(AbstractBaseModelAdmin[WorkflowStage]):
    """Админка этапов workflow."""

    list_display = ("id", "name", "workflow", "sort_order", "active", "created_at")
    list_display_links = ("name",)
    list_select_related = ("workflow",)
    search_fields = ("id", "name", "type")
    list_filter = ("is_initial", "is_final", "is_optional", "active")
    autocomplete_fields = ("workflow",)
