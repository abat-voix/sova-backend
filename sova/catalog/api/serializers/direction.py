from rest_framework import serializers

from sova.catalog.models import Direction


class DirectionShortSerializer(serializers.ModelSerializer):
    """Направление — краткое представление для вложенного использования."""

    class Meta:
        model = Direction
        fields = ("id", "name")


class DirectionSerializer(serializers.ModelSerializer):
    """Направление — представление для чтения (list/retrieve)."""

    class Meta:
        model = Direction
        fields = (
            "id",
            "name",
            "external_code",
            "is_active",
            "created_at",
            "updated_at",
        )


class WriteDirectionSerializer(serializers.ModelSerializer):
    """Направление — валидация входных данных (create/update)."""

    class Meta:
        model = Direction
        fields = (
            "id",
            "name",
            "external_code",
            "is_active",
        )
