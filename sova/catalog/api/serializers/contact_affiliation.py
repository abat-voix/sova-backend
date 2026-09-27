from django.db import transaction
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.catalog.api.serializers.b2c_client import B2CClientShortSerializer
from sova.catalog.api.serializers.contact_person import ContactPersonShortSerializer
from sova.catalog.api.serializers.product import ProductShortSerializer
from sova.catalog.api.serializers.university import UniversityShortSerializer
from sova.catalog.api.serializers.vendor import VendorShortSerializer
from sova.catalog.models import B2CClientContact, UniversityContact, VendorContact
from sova.catalog.services import contact_affiliation_service
from sova.core.api.validators import validate_model_constraints

_READ_FIELDS = ("id", "contact", "position", "preferred_channels", "created_at", "updated_at")
_WRITE_FIELDS = ("id", "contact", "position", "preferred_channels")


class _WriteAffiliationSerializer(serializers.ModelSerializer):
    """
    Общая запись связи: человек и организация задаются при создании и дальше не меняются.

    Другая организация — это другая связь. Ушёл из организации — связь удаляют (`DELETE`).
    """

    organization_field: str

    def validate(self, attrs: dict) -> dict:
        """Неизменяемость пары и одна связь на пару — 400 вместо ошибки БД."""
        if self.instance is not None:
            for field in ("contact", self.organization_field):
                if field in attrs and attrs[field] != getattr(self.instance, field):
                    raise serializers.ValidationError(
                        {field: _("Нельзя изменить после создания: создайте новую связь.")}
                    )
        validate_model_constraints(model=self.Meta.model, attrs=attrs, instance=self.instance)
        return attrs

    @transaction.atomic
    def create(self, validated_data: dict):
        """Новая связь включает выключенного человека: у него снова есть организация, где он работает."""
        instance = super().create(validated_data)
        contact_affiliation_service.activate_contact(contact=instance.contact)
        return instance


class UniversityContactSerializer(serializers.ModelSerializer):
    """Связь контактного лица с вузом (list/retrieve)."""

    contact = ContactPersonShortSerializer(read_only=True)
    university = UniversityShortSerializer(read_only=True)

    class Meta:
        model = UniversityContact
        fields = (*_READ_FIELDS, "university")


class WriteUniversityContactSerializer(_WriteAffiliationSerializer):
    """Связь контактного лица с вузом (create/update)."""

    organization_field = "university"

    class Meta:
        model = UniversityContact
        fields = (*_WRITE_FIELDS, "university")


class B2CClientContactSerializer(serializers.ModelSerializer):
    """Связь контактного лица с B2C-клиентом (list/retrieve)."""

    contact = ContactPersonShortSerializer(read_only=True)
    b2c_client = B2CClientShortSerializer(read_only=True)

    class Meta:
        model = B2CClientContact
        fields = (*_READ_FIELDS, "b2c_client")


class WriteB2CClientContactSerializer(_WriteAffiliationSerializer):
    """Связь контактного лица с B2C-клиентом (create/update)."""

    organization_field = "b2c_client"

    class Meta:
        model = B2CClientContact
        fields = (*_WRITE_FIELDS, "b2c_client")


class VendorContactSerializer(serializers.ModelSerializer):
    """Связь контактного лица с вендором и продукты, за которые он отвечает (list/retrieve)."""

    contact = ContactPersonShortSerializer(read_only=True)
    vendor = VendorShortSerializer(read_only=True)
    products = ProductShortSerializer(many=True, read_only=True)

    class Meta:
        model = VendorContact
        fields = (*_READ_FIELDS, "vendor", "products")


class WriteVendorContactSerializer(_WriteAffiliationSerializer):
    """Связь контактного лица с вендором (create/update); продукты — только этого вендора."""

    organization_field = "vendor"

    class Meta:
        model = VendorContact
        fields = (*_WRITE_FIELDS, "vendor", "products")

    def validate(self, attrs: dict) -> dict:
        """Продукты принадлежат вендору связи."""
        attrs = super().validate(attrs)
        vendor = attrs.get("vendor", getattr(self.instance, "vendor", None))
        foreign = [product.name for product in attrs.get("products", ()) if product.vendor_id != vendor.pk]
        if foreign:
            raise serializers.ValidationError(
                {"products": _("Продукты не принадлежат вендору: %s.") % ", ".join(foreign)}
            )
        return attrs
