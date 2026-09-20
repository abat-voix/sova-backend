from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.catalog.api.serializers import ITDirectionShortSerializer
from sova.interactions.models import InteractionDirection


class InteractionDirectionSerializer(serializers.ModelSerializer):
    """Направление взаимодействия — представление для чтения (list/retrieve)."""

    it_direction = ITDirectionShortSerializer(
        read_only=True,
        label=_("ИТ-направление"),
        help_text=_("Показывается развёрнуто, для записи см. write-сериализатор"),
    )

    class Meta:
        model = InteractionDirection
        fields = (
            "id",
            "interaction",
            "it_direction",
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
            "it_direction",
            "is_active",
        )
