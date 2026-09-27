from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework.validators import UniqueTogetherValidator

from sova.catalog.api.serializers import ProductShortSerializer
from sova.core.api.validators import validate_model_clean
from sova.interactions.api.serializers.fields import VisibleInteractionField
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

    # В модели interaction nullable ради headless-записей импорта договоров; через API
    # запись всегда создаётся в рамках взаимодействия. Условный unique-constraint модели DRF
    # не умеет проверять по FK в condition, поэтому уникальность задана явно в Meta.validators.
    interaction = VisibleInteractionField()

    class Meta:
        model = InteractionProduct
        fields = (
            "id",
            "interaction",
            "interaction_program",
            "product",
            "is_active",
        )
        validators = [
            UniqueTogetherValidator(
                queryset=InteractionProduct.objects.all(),
                fields=("interaction", "product"),
            ),
        ]

    def validate(self, attrs: dict) -> dict:
        """Проверка принадлежности программы взаимодействию и состава её каталога."""
        validate_model_clean(
            model=InteractionProduct,
            attrs=attrs,
            instance=self.instance,
        )
        return attrs
