from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.catalog.api.serializers.program import ProgramShortSerializer
from sova.catalog.api.serializers.vendor import VendorShortSerializer
from sova.catalog.models import Product
from sova.core.api.validators import validate_model_constraints


class ProductShortSerializer(serializers.ModelSerializer):
    """Продукт — краткое представление для вложенного использования."""

    class Meta:
        model = Product
        fields = ("id", "name")


class ProductSerializer(serializers.ModelSerializer):
    """Продукт — представление для чтения (list/retrieve)."""

    rank = serializers.IntegerField(
        read_only=True,
        allow_null=True,
        label=_("Место в рейтинге"),
        help_text=_("По числу взаимодействий, где продукт активен; при равенстве место делится. Null — места нет"),
    )
    vendor = VendorShortSerializer(
        read_only=True,
        label=_("Вендор"),
        help_text=_("Показывается развёрнуто, для записи см. write-сериализатор"),
    )
    programs = ProgramShortSerializer(
        many=True,
        read_only=True,
        label=_("Программы"),
        help_text=_("Показываются развёрнуто, для записи см. write-сериализатор"),
    )

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "external_code",
            "is_active",
            "vendor",
            "programs",
            "created_at",
            "updated_at",
            "rank",
        )


class WriteProductSerializer(serializers.ModelSerializer):
    """
    Продукт — валидация входных данных (create/update).

    Уникальность названия проверяется и у продуктов вендора, и среди продуктов
    без вендора — модель гарантирует её двумя ограничениями, из которых DRF
    самостоятельно понимает только безусловное.
    """

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "external_code",
            "is_active",
            "vendor",
            "programs",
        )

    def validate(self, attrs: dict) -> dict:
        """Уникальность названия в рамках вендора и кода без учёта регистра — 400 вместо ошибки БД."""
        validate_model_constraints(model=Product, attrs=attrs, instance=self.instance)
        return attrs
