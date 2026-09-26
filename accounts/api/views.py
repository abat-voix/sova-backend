from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.api.permissions import CanListUsers, IsPlatformAdmin
from accounts.api.serializers import (
    RoleChoiceSerializer,
    SetUserRoleSerializer,
    UserSerializer,
)
from accounts.models import SystemRole
from accounts.services import manageable_users, set_system_role, visible_users
from sova.core.api.views import SovaReadOnlyViewSet


class UserViewSet(SovaReadOnlyViewSet):
    """
    Пользователи системы и управление их прикладными ролями.

    Состав списка зависит от роли запрашивающего: руководитель видит КАМов,
    администратор платформы — всех активных пользователей, кроме себя.
    Остальным ролям список недоступен, а команды изменения роли доступны
    только администратору платформы.
    """

    read_serializer_class = UserSerializer
    serializer_class = UserSerializer
    permission_classes = (CanListUsers,)
    ordering_fields = ("last_name", "first_name", "email")
    search_fields = ("first_name", "last_name", "email", "username")

    def get_queryset(self) -> QuerySet:
        """Пользователи, видимые текущему пользователю согласно его роли."""
        if self.action == "role":
            return manageable_users(self.request.user)
        return (
            visible_users(self.request.user)
            .select_related("system_role")
            .order_by("last_name", "first_name", "pk")
        )

    def get_permissions(self):
        if self.action in {"role", "roles"}:
            return [IsPlatformAdmin()]
        return super().get_permissions()

    def get_serializer_class(self):
        if self.action == "role":
            return SetUserRoleSerializer
        if self.action == "roles":
            return RoleChoiceSerializer
        return super().get_serializer_class()

    @extend_schema(
        parameters=[],
        responses=RoleChoiceSerializer(many=True),
        operation_id="users_roles",
        description="Допустимые прикладные роли СОВА.",
    )
    @action(detail=False, methods=("get",), url_path="roles")
    def roles(self, request):
        choices = [
            {"value": value, "label": label}
            for value, label in SystemRole.choices
        ]
        return Response(self.get_serializer(choices, many=True).data)

    @extend_schema(
        request=SetUserRoleSerializer,
        responses=UserSerializer,
        operation_id="users_role_update",
        description="Назначить или снять прикладную роль пользователя.",
    )
    @action(detail=True, methods=("patch",), url_path="role")
    def role(self, request, pk=None):
        target = self.get_object()
        command = self.get_serializer(data=request.data)
        command.is_valid(raise_exception=True)
        user = set_system_role(
            actor=request.user,
            target=target,
            role=command.validated_data["role"],
        )
        return Response(UserSerializer(user, context=self.get_serializer_context()).data)
