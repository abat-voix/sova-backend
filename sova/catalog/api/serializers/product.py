from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.catalog.api.serializers.program import ProgramShortSerializer
from sova.catalog.api.serializers.vendor import VendorShortSerializer
from sova.catalog.models import Product


class ProductShortSerializer(serializers.ModelSerializer):
    """Продукт — краткое представление для вложенного использования."""

    class Meta:
        model = Product
        fields = ("id", "name")


class ProductSerializer(serializers.ModelSerializer):
    """Продукт — представление для чтения (list/retrieve)."""

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
        """Проверка уникальности названия продукта в рамках вендора."""
        name = attrs.get("name", getattr(self.instance, "name", None))
        vendor = attrs.get("vendor", getattr(self.instance, "vendor", None))

        duplicates = Product.objects.filter(name=name, vendor=vendor)
        if self.instance is not None:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise serializers.ValidationError(
                {"name": _("Продукт с таким названием у этого вендора уже существует.")},
            )
        return attrs
