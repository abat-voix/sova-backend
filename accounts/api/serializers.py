from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from accounts.models import SystemRole
from accounts.services import get_system_role
from sova.core.api.serializers import UserShortSerializer


class UserSerializer(UserShortSerializer):
    """Пользователь системы с его прикладной ролью в СОВА и руководителем."""

    role = serializers.SerializerMethodField(
        label=_("Роль в системе"),
        help_text=_("Код роли СОВА; null, если роль не назначена"),
    )
    role_display = serializers.SerializerMethodField(
        label=_("Роль в системе (название)"),
        help_text=_("Человекочитаемое название роли; null, если роль не назначена"),
    )
    head = UserShortSerializer(
        source="supervision.head",
        read_only=True,
        allow_null=True,
        label=_("Руководитель"),
        help_text=_("Руководитель КАМа; null, если не назначен или пользователь не КАМ"),
    )

    class Meta(UserShortSerializer.Meta):
        fields = (
            *UserShortSerializer.Meta.fields,
            "first_name",
            "last_name",
            "is_active",
            "role",
            "role_display",
            "head",
        )

    def get_role(self, instance) -> str | None:
        """Код прикладной роли пользователя."""
        return get_system_role(instance)

    def get_role_display(self, instance) -> str | None:
        """Название прикладной роли пользователя."""
        assignment = getattr(instance, "system_role", None)
        return assignment.get_role_display() if assignment else None


class ChangeRoleSerializer(serializers.Serializer):
    """Назначение, смена или снятие роли пользователя."""

    role = serializers.ChoiceField(
        choices=SystemRole.choices,
        allow_null=True,
        label=_("Роль в системе"),
        help_text=_("Новая роль; null снимает роль. Смена роли удаляет связи пользователя с руководителем и командой"),
    )


class SetHeadSerializer(serializers.Serializer):
    """Назначение или снятие руководителя КАМа."""

    head = serializers.PrimaryKeyRelatedField(
        queryset=get_user_model().objects.filter(is_active=True, system_role__role=SystemRole.HEAD),
        allow_null=True,
        label=_("Руководитель"),
        help_text=_("Id активного руководителя; null снимает руководителя"),
    )


class AccountChangeResultSerializer(serializers.Serializer):
    """Результат изменения пользователя."""

    user = UserSerializer(
        label=_("Пользователь"),
        help_text=_("Пользователь после изменения"),
    )
    orphaned_kams = UserShortSerializer(
        many=True,
        label=_("КАМы без руководителя"),
        help_text=_("КАМы, потерявшие руководителя из-за изменения; их нужно переназначить"),
    )
