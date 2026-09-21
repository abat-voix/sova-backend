from django.contrib import admin

from sova.core.admin import AbstractBaseModelAdmin
from sova.catalog.models import (
    B2CClient,
    ContactPerson,
    Direction,
    Product,
    Program,
    University,
    Vendor,
)


@admin.register(B2CClient)
class B2CClientAdmin(AbstractBaseModelAdmin[B2CClient]):
    """Админка B2C-клиентов."""

    list_display = ("id", "full_name", "kind", "phone", "is_active", "created_at")
    list_display_links = ("full_name",)
    search_fields = ("id", "full_name", "inn", "email", "phone")
    list_filter = ("kind", "is_active")


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


@admin.register(Direction)
class DirectionAdmin(AbstractBaseModelAdmin[Direction]):
    """Админка направлений."""

    list_display = ("id", "name", "external_code", "is_active", "created_at")
    list_display_links = ("name",)
    search_fields = ("id", "name", "external_code")
    list_filter = ("is_active",)


@admin.register(Product)
class ProductAdmin(AbstractBaseModelAdmin[Product]):
    """Админка продуктов."""

    list_display = ("id", "name", "vendor", "is_active", "created_at")
    list_display_links = ("name",)
    list_select_related = ("vendor",)
    search_fields = ("id", "name", "external_code")
    list_filter = ("is_active",)
    autocomplete_fields = ("vendor", "programs")


@admin.register(Program)
class ProgramAdmin(AbstractBaseModelAdmin[Program]):
    """Админка программ."""

    list_display = ("id", "name", "direction", "is_active", "created_at")
    list_display_links = ("name",)
    list_select_related = ("direction",)
    search_fields = ("id", "name")
    list_filter = ("is_active",)
    autocomplete_fields = ("direction",)


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
