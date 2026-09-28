from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.catalog.api.serializers.direction import DirectionShortSerializer
from sova.catalog.models import Program


class ProgramShortSerializer(serializers.ModelSerializer):
    """Программа — краткое представление для вложенного использования."""

    class Meta:
        model = Program
        fields = ("id", "name")


class ProgramSerializer(serializers.ModelSerializer):
    """Программа — представление для чтения (list/retrieve)."""

    rank = serializers.IntegerField(
        read_only=True,
        allow_null=True,
        label=_("Место в рейтинге"),
        help_text=_("По числу зачисленных (оплативших обучение) людей; при равенстве место делится. Null — места нет"),
    )
    direction = DirectionShortSerializer(
        read_only=True,
        label=_("Направление"),
        help_text=_("Показывается развёрнуто, для записи см. write-сериализатор"),
    )
    products_count = serializers.IntegerField(
        read_only=True,
        label=_("Количество продуктов"),
        help_text=_(
            "Продукты каталога, входящие в программу. "
            "Значение 0 — программа не зависит от продуктов",
        ),
    )

    class Meta:
        model = Program
        fields = (
            "id",
            "name",
            "is_active",
            "direction",
            "created_at",
            "updated_at",
            "rank",
            "products_count",
        )


class WriteProgramSerializer(serializers.ModelSerializer):
    """Программа — валидация входных данных (create/update)."""

    class Meta:
        model = Program
        fields = (
            "id",
            "name",
            "is_active",
            "direction",
        )
