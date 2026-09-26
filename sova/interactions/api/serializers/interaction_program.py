from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework.validators import UniqueTogetherValidator

from sova.catalog.api.serializers import DirectionShortSerializer, ProgramShortSerializer
from sova.interactions.models import Interaction, InteractionProgram


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

    # В модели interaction nullable ради headless-записей импорта договоров; через API
    # запись всегда создаётся в рамках взаимодействия. Условный unique-constraint модели DRF
    # не умеет проверять по FK в condition, поэтому уникальность задана явно в Meta.validators.
    interaction = serializers.PrimaryKeyRelatedField(
        queryset=Interaction.objects.all(),
        label=_("Взаимодействие"),
    )

    class Meta:
        model = InteractionProgram
        fields = (
            "id",
            "interaction",
            "program",
            "is_active",
        )
        validators = [
            UniqueTogetherValidator(
                queryset=InteractionProgram.objects.all(),
                fields=("interaction", "program"),
            ),
        ]
