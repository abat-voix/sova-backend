from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from sova.catalog.api.serializers.address import OrganizationAddressSerializer
from sova.catalog.models import Organization, OrganizationAddress
from sova.catalog.services import organization_address_service
from sova.core.api.validators import validate_model_constraints


class OrganizationShortSerializer(serializers.ModelSerializer):
    """Организация — краткое представление для вложенного использования."""

    class Meta:
        model = Organization
        fields = ("id", "name")


class OrganizationSerializer(serializers.ModelSerializer):
    """Организация — представление для чтения (list/retrieve)."""

    rank = serializers.IntegerField(
        read_only=True,
        allow_null=True,
        label=_("Место в рейтинге"),
        help_text=_("По числу зачисленных (оплативших обучение) людей; при равенстве место делится. Null — места нет"),
    )
    has_interactions = serializers.BooleanField(
        read_only=True,
        label=_("Наличие взаимодействий"),
        help_text=_("True — с организацией есть хотя бы одно взаимодействие"),
    )
    legal_address = serializers.SerializerMethodField(label=_("Юридический адрес"))
    actual_address = serializers.SerializerMethodField(
        label=_("Фактический адрес"),
        help_text=_("С учётом отметки «совпадает с юридическим»: тогда здесь юридический адрес"),
    )

    class Meta:
        model = Organization
        fields = (
            "id",
            "name",
            "inn",
            "external_code",
            "organization_type",
            "email",
            "phone",
            "is_active",
            "has_interactions",
            "created_at",
            "updated_at",
            "rank",
            "legal_address",
            "actual_address",
            "actual_same_as_legal",
        )

    @extend_schema_field(OrganizationAddressSerializer(allow_null=True))
    def get_legal_address(self, organization: Organization) -> dict | None:
        return self._address(organization_address_service.legal(organization))

    @extend_schema_field(OrganizationAddressSerializer(allow_null=True))
    def get_actual_address(self, organization: Organization) -> dict | None:
        return self._address(organization_address_service.actual(organization))

    @staticmethod
    def _address(address: OrganizationAddress | None) -> dict | None:
        return OrganizationAddressSerializer(address).data if address else None


class OrganizationMapPointSerializer(serializers.ModelSerializer):
    """Организация — облегчённая точка для карты без карточных данных."""

    has_interactions = serializers.BooleanField(
        read_only=True,
        label=_("Наличие взаимодействий"),
        help_text=_("True — с организацией есть хотя бы одно взаимодействие"),
    )

    lat = serializers.DecimalField(max_digits=9, decimal_places=6, read_only=True, label=_("Широта"))
    lon = serializers.DecimalField(max_digits=9, decimal_places=6, read_only=True, label=_("Долгота"))

    class Meta:
        model = Organization
        fields = ("id", "lat", "lon", "has_interactions")


class WriteOrganizationSerializer(serializers.ModelSerializer):
    """
    Организация — валидация входных данных (create/update). Адреса передаются вложенными объектами: `null` удаляет
    адрес, отсутствие ключа — не меняет. При `actual_same_as_legal` фактический адрес не хранится.
    """

    legal_address = OrganizationAddressSerializer(required=False, allow_null=True, label=_("Юридический адрес"))
    actual_address = OrganizationAddressSerializer(required=False, allow_null=True, label=_("Фактический адрес"))

    class Meta:
        model = Organization
        fields = (
            "id",
            "name",
            "inn",
            "external_code",
            "organization_type",
            "email",
            "phone",
            "is_active",
            "legal_address",
            "actual_address",
            "actual_same_as_legal",
        )

    def validate(self, attrs: dict) -> dict:
        """Уникальность названия и кода без учёта регистра — 400 вместо ошибки БД."""
        model_attrs = {key: value for key, value in attrs.items() if key not in ADDRESS_KEYS}
        validate_model_constraints(model=Organization, attrs=model_attrs, instance=self.instance)
        return attrs

    def create(self, validated_data: dict) -> Organization:
        addresses = self._pop_addresses(validated_data)
        organization = super().create(validated_data)
        organization_address_service.save(organization, addresses)
        return organization

    def update(self, instance: Organization, validated_data: dict) -> Organization:
        addresses = self._pop_addresses(validated_data)
        organization = super().update(instance, validated_data)
        organization_address_service.save(organization, addresses)
        return organization

    @staticmethod
    def _pop_addresses(validated_data: dict) -> dict:
        return {key: validated_data.pop(key) for key in ADDRESS_KEYS if key in validated_data}


# Поля адресов сохраняет `OrganizationAddressService`, а не модель организации
ADDRESS_KEYS = ("legal_address", "actual_address", "actual_same_as_legal")
