from django.db import transaction
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from sova.catalog.api.serializers.product import ProductShortSerializer
from sova.catalog.enum import ContactChannel
from sova.catalog.models import ContactPerson
from sova.catalog.services import contact_affiliation_service
from sova.core.text import normalize_telegram


class ContactPersonShortSerializer(serializers.ModelSerializer):
    """Контактное лицо — краткое представление для вложенного использования."""

    class Meta:
        model = ContactPerson
        fields = ("id", "full_name", "email", "phone", "telegram", "is_active")


class OrganizationShortSerializer(serializers.Serializer):
    """Организация связи — вуз, B2C-клиент или вендор."""

    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)


class ContactAffiliationSerializer(serializers.Serializer):
    """Связь человека с организацией любого типа — в составе контактного лица."""

    id = serializers.UUIDField(read_only=True)
    type = serializers.SerializerMethodField(help_text=_("university, b2c_client или vendor"))
    organization = serializers.SerializerMethodField()
    position = serializers.CharField(read_only=True)
    preferred_channels = serializers.ListField(
        child=serializers.ChoiceField(choices=ContactChannel.choices),
        read_only=True,
    )
    products = serializers.SerializerMethodField(help_text=_("Продукты вендора; у вуза и B2C-клиента — пусто"))

    @extend_schema_field(serializers.ChoiceField(choices=("university", "b2c_client", "vendor")))
    def get_type(self, affiliation) -> str:
        return contact_affiliation_service.type_code(
            organization=contact_affiliation_service.organization_of(affiliation=affiliation)
        )

    @extend_schema_field(OrganizationShortSerializer)
    def get_organization(self, affiliation) -> dict:
        organization = contact_affiliation_service.organization_of(affiliation=affiliation)
        return {"id": organization.pk, "name": str(organization)}

    @extend_schema_field(ProductShortSerializer(many=True))
    def get_products(self, affiliation) -> list:
        if not hasattr(affiliation, "products"):
            return []
        return ProductShortSerializer(affiliation.products.all(), many=True).data


class ContactPersonSerializer(serializers.ModelSerializer):
    """Контактное лицо — человек и все его связи с организациями (list/retrieve)."""

    affiliations = serializers.SerializerMethodField(
        help_text=_("Связи с организациями: должность и способы связи в каждой"),
    )

    class Meta:
        model = ContactPerson
        fields = (
            "id",
            "full_name",
            "email",
            "phone",
            "telegram",
            "is_active",
            "affiliations",
            "created_at",
            "updated_at",
        )

    @extend_schema_field(ContactAffiliationSerializer(many=True))
    def get_affiliations(self, contact: ContactPerson) -> list:
        return ContactAffiliationSerializer(contact_affiliation_service.links_of(contact=contact), many=True).data


class WriteContactPersonSerializer(serializers.ModelSerializer):
    """
    Контактное лицо — данные человека (create/update).

    Связь с организацией создаётся отдельно: `/university-contacts/`, `/b2c-client-contacts/`, `/vendor-contacts/`.
    """

    class Meta:
        model = ContactPerson
        fields = (
            "id",
            "full_name",
            "email",
            "phone",
            "telegram",
            "is_active",
        )

    def validate_telegram(self, value: str) -> str:
        """Ник без @ и ссылки t.me."""
        try:
            return normalize_telegram(value)
        except ValueError as error:
            raise serializers.ValidationError(str(error)) from error

    @transaction.atomic
    def update(self, instance: ContactPerson, validated_data: dict) -> ContactPerson:
        """Выключение человека — уход отовсюду: привязки к активным взаимодействиям закрываются, КАМы уведомлены, связи удаляются."""
        deactivating = instance.is_active and validated_data.get("is_active") is False
        instance = super().update(instance, validated_data)
        if deactivating:
            request = self.context.get("request")
            contact_affiliation_service.deactivate_contact(contact=instance, actor=getattr(request, "user", None))
        return instance


class PossibleDuplicatesQuerySerializer(serializers.Serializer):
    """Признаки человека, для которого ищутся возможные дубли."""

    full_name = serializers.CharField(required=False, allow_blank=True, default="")
    email = serializers.CharField(required=False, allow_blank=True, default="")
    phone = serializers.CharField(required=False, allow_blank=True, default="")
    telegram = serializers.CharField(required=False, allow_blank=True, default="")
    exclude = serializers.UUIDField(
        required=False,
        allow_null=True,
        default=None,
        help_text=_("ID самого контакта — при редактировании"),
    )

    def validate_telegram(self, value: str) -> str:
        """Некорректный ник не участвует в поиске."""
        try:
            return normalize_telegram(value)
        except ValueError:
            return ""
