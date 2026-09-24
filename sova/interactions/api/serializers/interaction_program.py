from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.catalog.api.serializers import DirectionShortSerializer, ProgramShortSerializer
from sova.interactions.models import InteractionProgram


class InteractionProgramSerializer(serializers.ModelSerializer):
    """Программа взаимодействия — представление для чтения (list/retrieve)."""

    program = ProgramShortSerializer(
        read_only=True,
        label=_("Программа"),
        help_text=_("Показывается развёрнуто, для записи см. write-сериализатор"),
    )
    direction = DirectionShortSerializer(
        source="program.direction",
        read_only=True,
        label=_("Направление"),
        help_text=_("Выводится из направления каталожной программы"),
    )

    class Meta:
        model = InteractionProgram
        fields = (
            "id",
            "interaction",
            "program",
            "direction",
            "is_active",
            "added_at",
        )


class WriteInteractionProgramSerializer(serializers.ModelSerializer):
    """Программа взаимодействия — валидация входных данных (create/update)."""

    class Meta:
        model = InteractionProgram
        fields = (
            "id",
            "interaction",
            "program",
            "is_active",
        )
