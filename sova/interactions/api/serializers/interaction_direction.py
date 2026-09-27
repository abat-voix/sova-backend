from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework.validators import UniqueTogetherValidator

from sova.catalog.api.serializers import DirectionShortSerializer
from sova.interactions.api.serializers.fields import VisibleInteractionField
from sova.interactions.models import InteractionDirection


class InteractionDirectionSerializer(serializers.ModelSerializer):
    """Направление взаимодействия — представление для чтения (list/retrieve)."""

    direction = DirectionShortSerializer(
        read_only=True,
        label=_("Направление"),
        help_text=_("Показывается развёрнуто, для записи см. write-сериализатор"),
    )

    class Meta:
        model = InteractionDirection
        fields = (
            "id",
            "interaction",
            "direction",
            "is_active",
            "added_at",
        )


class WriteInteractionDirectionSerializer(serializers.ModelSerializer):
    """Направление взаимодействия — валидация входных данных (create/update)."""

    # В модели interaction nullable ради headless-записей импорта договоров; через API
    # запись всегда создаётся в рамках взаимодействия. Условный unique-constraint модели DRF
    # не умеет проверять по FK в condition, поэтому уникальность задана явно в Meta.validators.
    interaction = VisibleInteractionField()

    class Meta:
        model = InteractionDirection
        fields = (
            "id",
            "interaction",
            "direction",
            "is_active",
        )
        validators = [
            UniqueTogetherValidator(
                queryset=InteractionDirection.objects.all(),
                fields=("interaction", "direction"),
            ),
        ]
