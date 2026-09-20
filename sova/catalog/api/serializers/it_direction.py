from rest_framework import serializers

from sova.catalog.models import ITDirection


class ITDirectionShortSerializer(serializers.ModelSerializer):
    """ИТ-направление — краткое представление для вложенного использования."""

    class Meta:
        model = ITDirection
        fields = ("id", "name")


class ITDirectionSerializer(serializers.ModelSerializer):
    """ИТ-направление — представление для чтения (list/retrieve)."""

    class Meta:
        model = ITDirection
        fields = (
            "id",
            "name",
            "external_code",
            "is_active",
            "created_at",
            "updated_at",
        )


class WriteITDirectionSerializer(serializers.ModelSerializer):
    """ИТ-направление — валидация входных данных (create/update)."""

    class Meta:
        model = ITDirection
        fields = (
            "id",
            "name",
            "external_code",
            "is_active",
        )
