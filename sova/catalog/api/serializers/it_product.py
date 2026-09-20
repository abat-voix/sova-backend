from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.catalog.api.serializers.it_program import ITProgramShortSerializer
from sova.catalog.api.serializers.vendor import VendorShortSerializer
from sova.catalog.models import ITProduct


class ITProductShortSerializer(serializers.ModelSerializer):
    """ИТ-продукт — краткое представление для вложенного использования."""

    class Meta:
        model = ITProduct
        fields = ("id", "name")


class ITProductSerializer(serializers.ModelSerializer):
    """ИТ-продукт — представление для чтения (list/retrieve)."""

    vendor = VendorShortSerializer(
        read_only=True,
        label=_("Вендор"),
        help_text=_("Показывается развёрнуто, для записи см. write-сериализатор"),
    )
    programs = ITProgramShortSerializer(
        many=True,
        read_only=True,
        label=_("ИТ-программы"),
        help_text=_("Показываются развёрнуто, для записи см. write-сериализатор"),
    )

    class Meta:
        model = ITProduct
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


class WriteITProductSerializer(serializers.ModelSerializer):
    """
    ИТ-продукт — валидация входных данных (create/update).

    Уникальность названия проверяется и у продуктов вендора, и среди продуктов
    без вендора — модель гарантирует её двумя ограничениями, из которых DRF
    самостоятельно понимает только безусловное.
    """

    class Meta:
        model = ITProduct
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

        duplicates = ITProduct.objects.filter(name=name, vendor=vendor)
        if self.instance is not None:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise serializers.ValidationError(
                {"name": _("Продукт с таким названием у этого вендора уже существует.")},
            )
        return attrs
