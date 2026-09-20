from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.catalog.api.serializers import ProductShortSerializer
from sova.core.api.validators import validate_model_clean
from sova.interactions.models import InteractionProduct


class InteractionProductShortSerializer(serializers.ModelSerializer):
    """Продукт взаимодействия — краткое представление для вложенного использования."""

    product = ProductShortSerializer(
        read_only=True,
        label=_("Продукт"),
        help_text=_("Показывается развёрнуто, для записи см. write-сериализатор"),
    )

    class Meta:
        model = InteractionProduct
        fields = ("id", "interaction", "product")


class InteractionProductSerializer(serializers.ModelSerializer):
    """Продукт взаимодействия — представление для чтения (list/retrieve)."""

    product = ProductShortSerializer(
        read_only=True,
        label=_("Продукт"),
        help_text=_("Показывается развёрнуто, для записи см. write-сериализатор"),
    )

    class Meta:
        model = InteractionProduct
        fields = (
            "id",
            "interaction",
            "interaction_program",
            "product",
            "is_active",
            "added_at",
        )


class WriteInteractionProductSerializer(serializers.ModelSerializer):
    """Продукт взаимодействия — валидация входных данных (create/update)."""

    class Meta:
        model = InteractionProduct
        fields = (
            "id",
            "interaction",
            "interaction_program",
            "product",
            "is_active",
        )

    def validate(self, attrs: dict) -> dict:
        """Проверка принадлежности программы взаимодействию и состава её каталога."""
        validate_model_clean(
            model=InteractionProduct,
            attrs=attrs,
            instance=self.instance,
        )
        return attrs
