from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.catalog.api.serializers.it_direction import ITDirectionShortSerializer
from sova.catalog.models import ITProgram


class ITProgramShortSerializer(serializers.ModelSerializer):
    """ИТ-программа — краткое представление для вложенного использования."""

    class Meta:
        model = ITProgram
        fields = ("id", "name")


class ITProgramSerializer(serializers.ModelSerializer):
    """ИТ-программа — представление для чтения (list/retrieve)."""

    it_direction = ITDirectionShortSerializer(
        read_only=True,
        label=_("ИТ-направление"),
        help_text=_("Показывается развёрнуто, для записи см. write-сериализатор"),
    )
    products_count = serializers.IntegerField(
        read_only=True,
        label=_("Количество продуктов"),
        help_text=_(
            "Продукты каталога, входящие в программу. "
            "Значение 0 — программа не зависит от ИТ-продуктов",
        ),
    )

    class Meta:
        model = ITProgram
        fields = (
            "id",
            "name",
            "is_active",
            "it_direction",
            "created_at",
            "updated_at",
            "products_count",
        )


class WriteITProgramSerializer(serializers.ModelSerializer):
    """ИТ-программа — валидация входных данных (create/update)."""

    class Meta:
        model = ITProgram
        fields = (
            "id",
            "name",
            "is_active",
            "it_direction",
        )
