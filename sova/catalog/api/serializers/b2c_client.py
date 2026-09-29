from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.catalog.api.serializers.address import B2CClientOpenAddressSerializer
from sova.catalog.models import B2CClient
from sova.catalog.services import b2c_client_address_service


class B2CClientShortSerializer(serializers.ModelSerializer):
    """B2C-клиент — краткое представление для вложенного использования."""

    class Meta:
        model = B2CClient
        fields = ("id", "full_name")


class B2CClientSerializer(serializers.ModelSerializer):
    """B2C-клиент — представление для чтения (list/retrieve)."""

    rank = serializers.IntegerField(
        read_only=True,
        allow_null=True,
        label=_("Место в рейтинге"),
        help_text=_("По числу зачисленных (оплативших обучение) людей; при равенстве место делится. Null — места нет"),
    )

    address = B2CClientOpenAddressSerializer(
        read_only=True,
        allow_null=True,
        label=_("Адрес"),
        help_text=_("Открытая часть адреса регистрации; улица и дом — в `registration-address/` по отдельному праву"),
    )

    class Meta:
        model = B2CClient
        fields = (
            "id",
            "full_name",
            "inn",
            "email",
            "phone",
            "is_active",
            "created_at",
            "updated_at",
            "rank",
            "address",
        )


class WriteB2CClientSerializer(serializers.ModelSerializer):
    """
    B2C-клиент — валидация входных данных (create/update). `address` — открытая часть адреса (страна, регион,
    город): `null` очищает её, отсутствие ключа — не меняет.
    """

    address = B2CClientOpenAddressSerializer(required=False, allow_null=True, label=_("Адрес"))

    class Meta:
        model = B2CClient
        fields = (
            "id",
            "full_name",
            "inn",
            "email",
            "phone",
            "is_active",
            "address",
        )
        # Длину ИНН проверяет validate_inn с понятным сообщением; стандартное «не более 12 символов» было бы лишним
        extra_kwargs = {"inn": {"max_length": None}}

    def create(self, validated_data: dict) -> B2CClient:
        address = validated_data.pop("address", ...)
        client = super().create(validated_data)
        if address is not ...:
            b2c_client_address_service.save_open(client, address)
        return client

    def update(self, instance: B2CClient, validated_data: dict) -> B2CClient:
        address = validated_data.pop("address", ...)
        client = super().update(instance, validated_data)
        if address is not ...:
            b2c_client_address_service.save_open(client, address)
        return client
