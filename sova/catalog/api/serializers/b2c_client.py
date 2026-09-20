from rest_framework import serializers

from sova.catalog.models import B2CClient


class B2CClientShortSerializer(serializers.ModelSerializer):
    """B2C-клиент — краткое представление для вложенного использования."""

    class Meta:
        model = B2CClient
        fields = ("id", "full_name", "kind")


class B2CClientSerializer(serializers.ModelSerializer):
    """B2C-клиент — представление для чтения (list/retrieve)."""

    class Meta:
        model = B2CClient
        fields = (
            "id",
            "full_name",
            "inn",
            "email",
            "phone",
            "kind",
            "is_active",
            "created_at",
            "updated_at",
        )


class WriteB2CClientSerializer(serializers.ModelSerializer):
    """B2C-клиент — валидация входных данных (create/update)."""

    class Meta:
        model = B2CClient
        fields = (
            "id",
            "full_name",
            "inn",
            "email",
            "phone",
            "kind",
            "is_active",
        )
