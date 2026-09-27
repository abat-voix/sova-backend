from django.contrib import admin

from sova.core.admin import AbstractBaseModelAdmin, AbstractHistoryModelAdmin
from sova.interactions.models import (
    Contract,
    ContractFile,
    DocumentTemplate,
    Interaction,
    InteractionContact,
    InteractionDirection,
    InteractionProduct,
    InteractionProgram,
    License,
    Responsible,
)


@admin.register(Contract)
class ContractAdmin(AbstractBaseModelAdmin[Contract]):
    """Админка договоров."""

    list_display = ("id", "contract_number", "interaction", "signed_at", "created_at")
    list_display_links = ("contract_number",)
    list_select_related = ("interaction",)
    search_fields = ("id", "contract_number")
    autocomplete_fields = ("interaction",)


@admin.register(ContractFile)
class ContractFileAdmin(AbstractHistoryModelAdmin[ContractFile]):
    """Журнал файлов договора. Запись создаётся системой — не редактируется."""

    list_display = ("id", "original_name", "contract", "uploaded_by", "uploaded_at")
    list_display_links = ("original_name",)
    list_select_related = ("contract", "uploaded_by")
    search_fields = ("id", "original_name")
    autocomplete_fields = ("contract", "uploaded_by")


@admin.register(DocumentTemplate)
class DocumentTemplateAdmin(AbstractBaseModelAdmin[DocumentTemplate]):
    """Шаблоны документов (docxtpl)."""

    list_display = ("id", "name", "kind", "is_active", "created_at")
    list_display_links = ("name",)
    list_filter = ("kind", "is_active")
    search_fields = ("id", "name")


@admin.register(Interaction)
class InteractionAdmin(AbstractBaseModelAdmin[Interaction]):
    """Админка взаимодействий."""

    list_display = ("display_number", "university", "b2c_client", "is_active", "created_at")
    list_select_related = ("university", "b2c_client")
    search_fields = ("id", "sequence_number", "comment", "university__name", "b2c_client__full_name")
    list_filter = ("is_active",)
    autocomplete_fields = ("university", "b2c_client")
    readonly_fields = ("sequence_number", "display_number")


@admin.register(InteractionContact)
class InteractionContactAdmin(AbstractBaseModelAdmin[InteractionContact]):
    """История привязок контактных лиц к взаимодействиям."""

    list_display = ("id", "interaction", "contact_person", "linked_at", "unlinked_at")
    list_select_related = ("interaction", "contact_person", "linked_by", "unlinked_by")
    search_fields = ("id", "contact_person__full_name")
    list_filter = ("unlinked_at",)
    autocomplete_fields = ("interaction", "contact_person", "linked_by", "unlinked_by")


@admin.register(InteractionDirection)
class InteractionDirectionAdmin(AbstractBaseModelAdmin[InteractionDirection]):
    """Админка направлений взаимодействия."""

    list_display = ("id", "interaction", "direction", "is_active", "added_at")
    list_select_related = ("interaction", "direction")
    search_fields = ("id", "direction__name")
    list_filter = ("is_active",)
    autocomplete_fields = ("interaction", "direction")


@admin.register(InteractionProduct)
class InteractionProductAdmin(AbstractBaseModelAdmin[InteractionProduct]):
    """Админка продуктов взаимодействия."""

    list_display = ("id", "interaction", "interaction_program", "product", "is_active", "added_at")
    list_select_related = ("interaction", "interaction_program", "product")
    search_fields = ("id", "product__name")
    list_filter = ("is_active",)
    autocomplete_fields = ("interaction", "interaction_program", "product")


@admin.register(InteractionProgram)
class InteractionProgramAdmin(AbstractBaseModelAdmin[InteractionProgram]):
    """Админка программ взаимодействия."""

    list_display = ("id", "interaction", "program", "is_active", "added_at")
    list_select_related = ("interaction", "program")
    search_fields = ("id", "program__name")
    list_filter = ("is_active",)
    autocomplete_fields = ("interaction", "program")


@admin.register(License)
class LicenseAdmin(AbstractBaseModelAdmin[License]):
    """Админка лицензий."""

    list_display = ("id", "contract", "interaction_product", "is_signed", "is_active", "created_at")
    list_select_related = ("contract", "interaction_product")
    search_fields = ("id",)
    list_filter = ("is_signed", "is_active")
    autocomplete_fields = ("contract", "interaction_product", "created_by")


@admin.register(Responsible)
class ResponsibleAdmin(AbstractBaseModelAdmin[Responsible]):
    """Админка назначений ответственных на взаимодействие или договор."""

    list_display = ("id", "interaction", "contract", "manager", "assigned_by", "assigned_at")
    list_select_related = ("interaction", "contract", "manager", "assigned_by")
    list_filter = (("interaction", admin.EmptyFieldListFilter),)
    search_fields = ("id",)
    autocomplete_fields = ("interaction", "contract", "manager", "assigned_by")
