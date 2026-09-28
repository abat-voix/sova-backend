from django import forms
from django.contrib import admin, messages

from sova.catalog.models import (
    B2CClient,
    B2CClientAddress,
    B2CClientAddressAccessLog,
    B2CClientContact,
    CatalogImportMapping,
    ContactPerson,
    Direction,
    Product,
    Program,
    Organization,
    OrganizationAddress,
    OrganizationContact,
    Vendor,
    VendorContact,
)
from sova.catalog.models.contact_affiliation import AbstractContactAffiliation
from sova.catalog.services import b2c_client_address_service, contact_affiliation_service
from sova.core.admin import AbstractBaseModelAdmin


class B2CClientAddressInline(admin.StackedInline):
    """Открытая часть адреса: улица, дом, квартира и индекс — персональные данные, в админке не показываются."""

    model = B2CClientAddress
    fields = ("country_code", "region", "city")
    extra = 0
    max_num = 1


@admin.register(B2CClient)
class B2CClientAdmin(AbstractBaseModelAdmin[B2CClient]):
    """Админка B2C-клиентов."""

    list_display = ("id", "full_name", "phone", "is_active", "created_at")
    list_display_links = ("full_name",)
    search_fields = ("id", "full_name", "inn", "email", "phone")
    list_filter = ("is_active",)
    inlines = (B2CClientAddressInline,)


@admin.register(B2CClientAddressAccessLog)
class B2CClientAddressAccessLogAdmin(AbstractBaseModelAdmin[B2CClientAddressAccessLog]):
    """Журнал доступа к адресам B2C-клиентов — только чтение и только администратору платформы."""

    list_display = ("accessed_at", "user", "b2c_client", "action", "fields", "ip")
    list_filter = ("action",)
    search_fields = ("b2c_client__full_name", "user__username")

    def has_module_permission(self, request):
        return b2c_client_address_service.can_read(request.user) and super().has_module_permission(request)

    def has_view_permission(self, request, obj=None):
        return b2c_client_address_service.can_read(request.user) and super().has_view_permission(request, obj)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CatalogImportMapping)
class CatalogImportMappingAdmin(AbstractBaseModelAdmin[CatalogImportMapping]):
    """Админка настраиваемого маппинга импорта каталогов."""

    list_display = ("id", "catalog_type", "source_column", "target_field", "updated_at")
    list_display_links = ("source_column",)
    list_filter = ("catalog_type",)
    search_fields = ("source_column", "target_field")


class ContactAffiliationFormsetMixin:
    """
    Связи в inline сохраняются по правилам сервиса связей, а не напрямую.

    Удаление связи — уход из организации: человек отвязывается от её активных взаимодействий, КАМы уведомлены.
    Новая связь включает выключенного человека.
    """

    def save_formset(self, request, form, formset, change) -> None:
        if not issubclass(formset.model, AbstractContactAffiliation):
            super().save_formset(request, form, formset, change)
            return

        instances = formset.save(commit=False)
        for affiliation in formset.deleted_objects:
            closed = contact_affiliation_service.delete(affiliation=affiliation, actor=request.user)
            if closed:
                messages.warning(
                    request,
                    f"{affiliation}: связь удалена, отвязано от взаимодействий — {len(closed)}, КАМы уведомлены.",
                )

        for affiliation in instances:
            created = affiliation._state.adding
            affiliation.save()
            if created:
                contact_affiliation_service.activate_contact(contact=affiliation.contact)
        formset.save_m2m()


class ContactAffiliationInlineForm(forms.ModelForm):
    """Человек и организация существующей связи не меняются: другая организация — другая связь (как в API)."""

    locked_fields = ("contact", "organization", "b2c_client", "vendor")

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # pk у новой связи задан сразу (UUID по умолчанию) — существующую отличает только _state.adding.
        if not self.instance._state.adding:
            for name in self.locked_fields:
                if name in self.fields:
                    self.fields[name].disabled = True


class OrganizationContactInline(admin.TabularInline):
    """Связи контактного лица с организациями."""

    model = OrganizationContact
    form = ContactAffiliationInlineForm
    extra = 0
    fields = ("organization", "position", "preferred_channels")
    autocomplete_fields = ("organization",)


class B2CClientContactInline(admin.TabularInline):
    """Связи контактного лица с B2C-клиентами."""

    model = B2CClientContact
    form = ContactAffiliationInlineForm
    extra = 0
    fields = ("b2c_client", "position", "preferred_channels")
    autocomplete_fields = ("b2c_client",)


class VendorContactInline(admin.TabularInline):
    """Связи контактного лица с вендорами."""

    model = VendorContact
    form = ContactAffiliationInlineForm
    extra = 0
    fields = ("vendor", "position", "preferred_channels", "products")
    autocomplete_fields = ("vendor", "products")


class VendorContactOfVendorInline(admin.TabularInline):
    """Контактные лица вендора."""

    model = VendorContact
    form = ContactAffiliationInlineForm
    extra = 0
    fields = ("contact", "position", "preferred_channels", "products")
    autocomplete_fields = ("contact", "products")


@admin.register(ContactPerson)
class ContactPersonAdmin(ContactAffiliationFormsetMixin, AbstractBaseModelAdmin[ContactPerson]):
    """Админка контактных лиц: человек и его связи с организациями."""

    list_display = ("id", "full_name", "email", "phone", "telegram", "is_active", "created_at")
    list_display_links = ("full_name",)
    search_fields = (
        "id",
        "full_name",
        "email",
        "phone",
        "telegram",
        "organization_links__organization__name",
        "b2c_client_links__b2c_client__full_name",
        "vendor_links__vendor__name",
    )
    list_filter = ("is_active",)
    inlines = (OrganizationContactInline, B2CClientContactInline, VendorContactInline)

    def save_related(self, request, form, formsets, change) -> None:
        """
        Выключение человека — уход отовсюду (`deactivate_contact`): привязки закрываются, связи удаляются.

        После inline, чтобы новая связь в той же форме не включила человека обратно; решение «выключают»
        принимается до inline.
        """
        deactivating = change and "is_active" in form.changed_data and not form.instance.is_active
        super().save_related(request, form, formsets, change)
        if deactivating:
            closed = contact_affiliation_service.deactivate_contact(contact=form.instance, actor=request.user)
            messages.warning(
                request, f"{form.instance}: выключен, связи удалены, отвязано от взаимодействий — {len(closed)}."
            )


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


class OrganizationAddressInline(admin.StackedInline):
    model = OrganizationAddress
    extra = 0
    max_num = 2


@admin.register(Organization)
class OrganizationAdmin(AbstractBaseModelAdmin[Organization]):
    """Админка организаций."""

    list_display = ("id", "name", "inn", "organization_type", "is_active", "created_at")
    list_display_links = ("name",)
    search_fields = ("id", "name", "inn", "external_code")
    list_filter = ("organization_type", "is_active")
    inlines = (OrganizationAddressInline,)


@admin.register(Vendor)
class VendorAdmin(ContactAffiliationFormsetMixin, AbstractBaseModelAdmin[Vendor]):
    """Админка вендоров."""

    list_display = ("id", "name", "external_code", "is_active", "created_at")
    list_display_links = ("name",)
    search_fields = ("id", "name", "external_code")
    list_filter = ("is_active",)
    inlines = (VendorContactOfVendorInline,)
