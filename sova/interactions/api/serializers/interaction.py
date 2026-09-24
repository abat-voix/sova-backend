from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from sova.catalog.api.serializers import (
    B2CClientShortSerializer,
    UniversityShortSerializer,
)
from sova.core.api.validators import validate_exactly_one_counterparty
from sova.interactions.api.serializers.responsible import ResponsibleShortSerializer
from sova.interactions.models import Interaction


class InteractionShortSerializer(serializers.ModelSerializer):
    """Взаимодействие — краткое представление для вложенного использования."""

    university = UniversityShortSerializer(
        read_only=True,
        label=_("Вуз"),
        help_text=_("Показывается развёрнуто; пусто у взаимодействий с B2C-клиентом"),
    )
    b2c_client = B2CClientShortSerializer(
        read_only=True,
        label=_("B2C-клиент"),
        help_text=_("Показывается развёрнуто; пусто у взаимодействий с вузом"),
    )

    class Meta:
        model = Interaction
        fields = ("id", "university", "b2c_client")


class InteractionSerializer(serializers.ModelSerializer):
    """Взаимодействие — представление для чтения (list/retrieve)."""

    university = UniversityShortSerializer(
        read_only=True,
        label=_("Вуз"),
        help_text=_("Показывается развёрнуто; пусто у взаимодействий с B2C-клиентом"),
    )
    b2c_client = B2CClientShortSerializer(
        read_only=True,
        label=_("B2C-клиент"),
        help_text=_("Показывается развёрнуто; пусто у взаимодействий с вузом"),
    )
    current_responsibles = serializers.SerializerMethodField(
        label=_("Действующие ответственные"),
        help_text=_("Назначения без даты снятия в порядке назначения; пустой список, если КАМ не назначен"),
    )
    directions_count = serializers.IntegerField(
        read_only=True,
        label=_("Количество направлений"),
        help_text=_("Считается через annotate() по активным направлениям взаимодействия"),
    )
    programs_count = serializers.IntegerField(
        read_only=True,
        label=_("Количество программ"),
        help_text=_("Считается через annotate() по активным программам взаимодействия"),
    )
    products_count = serializers.IntegerField(
        read_only=True,
        label=_("Количество продуктов"),
        help_text=_("Считается через annotate() по активным продуктам взаимодействия"),
    )

    class Meta:
        model = Interaction
        fields = (
            "id",
            "comment",
            "is_active",
            "university",
            "b2c_client",
            "created_at",
            "updated_at",
            "current_responsibles",
            "directions_count",
            "programs_count",
            "products_count",
        )

    @extend_schema_field(ResponsibleShortSerializer(many=True))
    def get_current_responsibles(self, instance: Interaction) -> list[dict]:
        """
        Возвращает действующих ответственных.

        ViewSet заранее подгружает его через Prefetch(to_attr="current_responsibles"),
        поэтому запрос на каждую строку списка не выполняется.
        """
        current = getattr(instance, "current_responsibles", None)
        if current is None:
            current = list(
                instance.responsibles
                .filter(unassigned_at__isnull=True)
                .select_related("manager")
                .order_by("assigned_at", "pk"),
            )
        return ResponsibleShortSerializer(current, many=True, context=self.context).data


class WriteInteractionSerializer(serializers.ModelSerializer):
    """Взаимодействие — валидация входных данных (create/update)."""

    class Meta:
        model = Interaction
        fields = (
            "id",
            "comment",
            "is_active",
            "university",
            "b2c_client",
        )

    def validate(self, attrs: dict) -> dict:
        """Проверка, что задан ровно один контрагент."""
        validate_exactly_one_counterparty(attrs=attrs, instance=self.instance)
        return attrs
