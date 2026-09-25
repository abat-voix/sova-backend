from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.core.api.serializers import UserShortSerializer
from sova.interactions.models import Responsible
from sova.interactions.services.responsible_policy import assignable_managers, removable_managers


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


class ActorManagerField(serializers.PrimaryKeyRelatedField):
    """Менеджер из набора, допустимого для пользователя запроса (`responsible_policy`)."""

    def __init__(self, managers, **kwargs) -> None:
        self.managers = managers
        # Полный queryset — для схемы API; проверка идёт по `get_queryset`
        super().__init__(queryset=get_user_model().objects.all(), **kwargs)

    def get_queryset(self):
        """Допустимые менеджеры для пользователя запроса."""
        return self.managers(self.context["request"].user)


class AssignResponsibleSerializer(serializers.Serializer):
    """Назначение ответственного менеджера на взаимодействие."""

    manager = ActorManagerField(
        managers=assignable_managers,
        label=_("Ответственный менеджер"),
        help_text=_(
            "Id пользователя: администратор — активный КАМ или руководитель; руководитель — он сам, КАМ его "
            "команды или свободный (вступит в команду); КАМ — только он сам. Уже назначенный не дублируется",
        ),
        error_messages={"does_not_exist": _("Этого менеджера нельзя назначить ответственным.")},
    )


class UnassignResponsibleSerializer(serializers.Serializer):
    """Снятие ответственного менеджера с взаимодействия."""

    manager = ActorManagerField(
        managers=removable_managers,
        label=_("Ответственный менеджер"),
        help_text=_(
            "Id менеджера: администратор — любой; руководитель — он сам, КАМ его команды или неактивный КАМ. "
            "Остальные ответственные остаются",
        ),
        error_messages={"does_not_exist": _("Этого менеджера нельзя снять.")},
    )
