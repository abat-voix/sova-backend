from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.catalog.api.serializers import DirectionShortSerializer
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

    class Meta:
        model = InteractionDirection
        fields = (
            "id",
            "interaction",
            "direction",
            "is_active",
        )
