from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from accounts.models import SystemRole
from accounts.services import get_system_role
from sova.core.api.serializers import UserShortSerializer


class UserSerializer(UserShortSerializer):
    """Пользователь системы с его прикладной ролью в СОВА."""

    role = serializers.SerializerMethodField(
        label=_("Роль в системе"),
        help_text=_("Код роли СОВА; null, если роль не назначена"),
    )
    role_display = serializers.SerializerMethodField(
        label=_("Роль в системе (название)"),
        help_text=_("Человекочитаемое название роли; null, если роль не назначена"),
    )

    class Meta(UserShortSerializer.Meta):
        fields = (
            *UserShortSerializer.Meta.fields,
            "first_name",
            "last_name",
            "role",
            "role_display",
        )

    def get_role(self, instance) -> str | None:
        """Код прикладной роли пользователя."""
        return get_system_role(instance)

    def get_role_display(self, instance) -> str | None:
        """Название прикладной роли пользователя."""
        assignment = getattr(instance, "system_role", None)
        return assignment.get_role_display() if assignment else None


class RoleChoiceSerializer(serializers.Serializer):
    """Человекочитаемый справочник ролей СОВА."""

    value = serializers.CharField()
    label = serializers.CharField()


class SetUserRoleSerializer(serializers.Serializer):
    """Команда назначения единственной роли пользователя."""

    role = serializers.ChoiceField(
        choices=SystemRole.choices,
        allow_null=True,
        required=True,
        help_text="Код роли СОВА или null для снятия роли.",
    )
