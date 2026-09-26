from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.catalog.models import University
from sova.core.api.validators import validate_model_constraints


class UniversityShortSerializer(serializers.ModelSerializer):
    """Вуз — краткое представление для вложенного использования."""

    class Meta:
        model = University
        fields = ("id", "name")


class UniversitySerializer(serializers.ModelSerializer):
    """Вуз — представление для чтения (list/retrieve)."""

    has_interactions = serializers.BooleanField(
        read_only=True,
        label=_("Наличие взаимодействий"),
        help_text=_("True — с вузом есть хотя бы одно взаимодействие"),
    )

    class Meta:
        model = University
        fields = (
            "id",
            "name",
            "inn",
            "external_code",
            "email",
            "phone",
            "is_active",
            "has_interactions",
            "created_at",
            "updated_at",
            "lat",
            "lon",
            "city",
        )


class UniversityMapPointSerializer(serializers.ModelSerializer):
    """Вуз — облегчённая точка для карты без карточных данных."""

    has_interactions = serializers.BooleanField(
        read_only=True,
        label=_("Наличие взаимодействий"),
        help_text=_("True — с вузом есть хотя бы одно взаимодействие"),
    )

    class Meta:
        model = University
        fields = ("id", "lat", "lon", "has_interactions")


class WriteUniversitySerializer(serializers.ModelSerializer):
    """Вуз — валидация входных данных (create/update)."""

    class Meta:
        model = University
        fields = (
            "id",
            "name",
            "inn",
            "external_code",
            "email",
            "phone",
            "is_active",
        )

    def validate(self, attrs: dict) -> dict:
        """Уникальность названия и кода без учёта регистра — 400 вместо ошибки БД."""
        validate_model_constraints(model=University, attrs=attrs, instance=self.instance)
        return attrs
