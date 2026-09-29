from django.db import transaction
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.catalog.api.serializers.b2c_client import B2CClientShortSerializer
from sova.catalog.api.serializers.contact_person import ContactPersonShortSerializer, WriteContactPersonSerializer
from sova.catalog.api.serializers.product import ProductShortSerializer
from sova.catalog.api.serializers.organization import OrganizationShortSerializer
from sova.catalog.api.serializers.vendor import VendorShortSerializer
from sova.catalog.enum import ContactChannel
from sova.catalog.models import B2CClientContact, ContactPerson, OrganizationContact, VendorContact
from sova.catalog.services import contact_affiliation_service
from sova.core.api.validators import validate_model_constraints

_READ_FIELDS = ("id", "contact", "position", "preferred_channels", "created_at", "updated_at")
_WRITE_FIELDS = ("id", "contact", "new_contact", "position", "preferred_channels")


class _WriteAffiliationSerializer(serializers.ModelSerializer):
    """
    Общая запись связи: человек и организация задаются при создании и дальше не меняются.

    Человек — существующий (`contact`) или новый (`new_contact`): новый создаётся вместе со связью в одной
    транзакции, поэтому ошибка связи не оставляет человека без организации. Другая организация — это другая
    связь. Ушёл из организации — связь удаляют (`DELETE`).
    """

    organization_field: str

    contact = serializers.PrimaryKeyRelatedField(
        queryset=ContactPerson.objects.all(),
        required=False,
        label=_("Контактное лицо"),
        help_text=_("Существующий человек; не задан — передайте `new_contact`"),
    )
    new_contact = WriteContactPersonSerializer(
        required=False,
        write_only=True,
        label=_("Новое контактное лицо"),
        help_text=_("Данные нового человека — создаётся вместе со связью; только при создании, вместо `contact`"),
    )

    def get_unique_together_validators(self) -> list:
        """
        Без автоматического UniqueTogetherValidator: он делает `contact` обязательным, а с `new_contact` человека
        ещё нет. Одну связь на пару проверяет `validate_model_constraints`.
        """
        return []

    def validate(self, attrs: dict) -> dict:
        """Ровно один человек при создании, неизменяемость пары, одна связь на пару и заполненные способы связи."""
        if self.instance is None:
            if ("contact" in attrs) == ("new_contact" in attrs):
                raise serializers.ValidationError(_("Укажите существующего человека (contact) или нового (new_contact)."))
        else:
            if "new_contact" in attrs:
                raise serializers.ValidationError({"new_contact": _("Только при создании связи.")})
            for field in ("contact", self.organization_field):
                if field in attrs and attrs[field] != getattr(self.instance, field):
                    raise serializers.ValidationError(
                        {field: _("Нельзя изменить после создания: создайте новую связь.")}
                    )
        validate_model_constraints(model=self.Meta.model, attrs=attrs, instance=self.instance)
        self._validate_channels(attrs)
        return attrs

    def _validate_channels(self, attrs: dict) -> None:
        """Выбранный способ связи требует заполненного поля у человека: «Телефон» — телефон и т. д."""
        channels = attrs.get("preferred_channels", getattr(self.instance, "preferred_channels", []))
        person = attrs.get("new_contact")
        if person is None:
            contact = attrs.get("contact", getattr(self.instance, "contact", None))
            person = {field: getattr(contact, field) for field in ("email", "phone", "telegram")}
        unfilled = contact_affiliation_service.unfilled_channels(
            channels=channels,
            email=person.get("email", ""),
            phone=person.get("phone", ""),
            telegram=person.get("telegram", ""),
        )
        if unfilled:
            labels = ", ".join(f"«{ContactChannel(channel).label}»" for channel in unfilled)
            raise serializers.ValidationError(
                {"preferred_channels": _("У контакта не заполнены данные для способа связи: %s.") % labels}
            )

    @transaction.atomic
    def create(self, validated_data: dict):
        """Новый человек создаётся вместе со связью; новая связь включает выключенного человека."""
        new_contact = validated_data.pop("new_contact", None)
        if new_contact is not None:
            validated_data["contact"] = ContactPerson.objects.create(**new_contact)
        instance = super().create(validated_data)
        contact_affiliation_service.activate_contact(contact=instance.contact)
        return instance


class OrganizationContactSerializer(serializers.ModelSerializer):
    """Связь контактного лица с организацией (list/retrieve)."""

    contact = ContactPersonShortSerializer(read_only=True)
    organization = OrganizationShortSerializer(read_only=True)

    class Meta:
        model = OrganizationContact
        fields = (*_READ_FIELDS, "organization")


class WriteOrganizationContactSerializer(_WriteAffiliationSerializer):
    """Связь контактного лица с организацией (create/update)."""

    organization_field = "organization"

    class Meta:
        model = OrganizationContact
        fields = (*_WRITE_FIELDS, "organization")


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
