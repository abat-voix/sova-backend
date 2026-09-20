from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.core.api.serializers import UserShortSerializer
from sova.interactions.models import Responsible


class ResponsibleShortSerializer(serializers.ModelSerializer):
    """Назначение ответственного — краткое представление для вложенного использования."""

    manager = UserShortSerializer(
        read_only=True,
        label=_("Ответственный менеджер"),
        help_text=_("Менеджер, ведущий взаимодействие"),
    )

    class Meta:
        model = Responsible
        fields = ("id", "manager", "assigned_at")


class ResponsibleSerializer(serializers.ModelSerializer):
    """Назначение ответственного — представление для чтения (list/retrieve)."""

    interaction = serializers.PrimaryKeyRelatedField(
        read_only=True,
        label=_("Взаимодействие"),
        help_text=_("Id взаимодействия, за которое назначен ответственный"),
    )
    manager = UserShortSerializer(
        read_only=True,
        label=_("Ответственный менеджер"),
        help_text=_("Менеджер, ведущий взаимодействие"),
    )
    assigned_by = UserShortSerializer(
        read_only=True,
        label=_("Назначил"),
        help_text=_("Пользователь, выполнивший назначение; пусто, если он удалён"),
    )

    class Meta:
        model = Responsible
        fields = (
            "id",
            "interaction",
            "manager",
            "assigned_by",
            "assigned_at",
            "unassigned_at",
        )


class AssignResponsibleSerializer(serializers.Serializer):
    """Назначение ответственного менеджера на взаимодействие."""

    manager = serializers.PrimaryKeyRelatedField(
        queryset=get_user_model().objects.filter(is_active=True),
        label=_("Ответственный менеджер"),
        help_text=_(
            "Id активного пользователя; действующий ответственный, "
            "если он есть, будет заменён с сохранением истории",
        ),
    )
