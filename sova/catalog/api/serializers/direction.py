from rest_framework import serializers

from sova.catalog.models import Direction
from sova.core.api.validators import validate_model_constraints


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

    def validate(self, attrs: dict) -> dict:
        """Уникальность названия и кода без учёта регистра — 400 вместо ошибки БД."""
        validate_model_constraints(model=Direction, attrs=attrs, instance=self.instance)
        return attrs
