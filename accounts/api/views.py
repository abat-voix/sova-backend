from django.db.models import QuerySet
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from accounts.api.exceptions import AccountRuleError
from accounts.api.filters import UserFilter
from accounts.api.permissions import CanListUsers, IsHead, IsPlatformAdmin
from accounts.api.serializers import (
    AccountChangeResultSerializer,
    ChangeRoleSerializer,
    RoleChoiceSerializer,
    SetHeadSerializer,
    UserSerializer,
)
from accounts.exceptions import KamHasHeadError, NotInTeamError
from accounts.models import SystemRole
from accounts.services import account_service, get_system_role, visible_users
from sova.core.api.exceptions import ConflictError
from sova.core.api.views import SovaReadOnlyViewSet


class UserViewSet(SovaReadOnlyViewSet):
    """
    Пользователи системы и управление ими.

    Состав списка зависит от роли запрашивающего: руководитель видит активных КАМов своей команды и свободных,
    администратор платформы — всех пользователей. Список по умолчанию содержит только активных, неактивных отдаёт
    фильтр `is_active=false`. Фильтры `team` (`mine`/`free`), `role` (несколько значений) и `head` сужают список.
    Остальным ролям эндпоинт недоступен. Экшен `roles` — справочник ролей для тех же ролей.

    Экшены `role`, `head`, `deactivate`, `activate` — только для администратора платформы. Смена роли и деактивация
    удаляют связи пользователя с руководителем и командой; КАМы, оставшиеся без руководителя, возвращаются в
    `orphaned_kams`, чтобы их переназначить.

    Экшены `claim` / `release` — только для руководителя: он забирает свободного КАМа в свою команду и отпускает
    своего. КАМа другого руководителя забрать нельзя (409 `kam_has_head`).
    """

    read_serializer_class = UserSerializer
    serializer_class = UserSerializer
    permission_classes = (CanListUsers,)
    filterset_class = UserFilter
    ordering_fields = ("last_name", "first_name", "email")
    search_fields = ("first_name", "last_name", "email", "username")

    def get_queryset(self) -> QuerySet:
        """Пользователи, видимые текущему пользователю согласно его роли; в списке по умолчанию — активные."""
        queryset = visible_users(self.request.user)
        if self.action == "list" and "is_active" not in self.request.query_params:
            queryset = queryset.filter(is_active=True)
        return queryset.select_related("system_role", "supervision__head").order_by("last_name", "first_name", "pk")

    @extend_schema(request=None, responses={200: RoleChoiceSerializer(many=True)})
    @action(
        methods=["GET"],
        detail=False,
        url_path="roles",
        serializer_class=RoleChoiceSerializer,
        pagination_class=None,
    )
    def roles(self, request: Request) -> Response:
        """Справочник ролей СОВА: код для `role` в запросах и название."""
        choices = [{"value": value, "label": label} for value, label in SystemRole.choices]
        return Response(data=self.get_serializer(choices, many=True).data, status=status.HTTP_200_OK)

    @extend_schema(request=ChangeRoleSerializer, responses={200: AccountChangeResultSerializer})
    @action(
        methods=["PUT"],
        detail=True,
        url_path="role",
        serializer_class=ChangeRoleSerializer,
        permission_classes=(IsPlatformAdmin,),
    )
    def role(self, request: Request, pk=None) -> Response:
        """Назначает, меняет или снимает роль пользователя. Снять роль администратора с себя нельзя."""
        user = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        role = serializer.validated_data["role"]
        if user.pk == request.user.pk and role != SystemRole.PLATFORM_ADMIN:
            raise AccountRuleError(
                detail=_("Нельзя снять роль администратора платформы с самого себя."),
                code="self_lockout",
            )

        orphans = account_service.change_role(user=user, role=role, actor=request.user)
        return self._result(user=user, orphans=orphans)

    @extend_schema(request=SetHeadSerializer, responses={200: AccountChangeResultSerializer})
    @action(
        methods=["PUT"],
        detail=True,
        url_path="head",
        serializer_class=SetHeadSerializer,
        permission_classes=(IsPlatformAdmin,),
    )
    def head(self, request: Request, pk=None) -> Response:
        """Назначает или снимает (`head: null`) руководителя активного КАМа."""
        user = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        head = serializer.validated_data["head"]

        if head is None:
            account_service.remove_supervisor(kam=user, actor=request.user)
        else:
            if not user.is_active or get_system_role(user) != SystemRole.KAM:
                raise AccountRuleError(
                    detail=_("Руководителя назначают только активному пользователю с ролью «КАМ»."),
                    code="invalid_supervision",
                )
            account_service.set_supervisor(kam=user, head=head, actor=request.user)
        return self._result(user=user, orphans=[])

    @extend_schema(request=None, responses={200: AccountChangeResultSerializer})
    @action(methods=["POST"], detail=True, url_path="deactivate", permission_classes=(IsPlatformAdmin,))
    def deactivate(self, request: Request, pk=None) -> Response:
        """Деактивирует пользователя. Деактивировать самого себя нельзя."""
        user = self.get_object()
        if user.pk == request.user.pk:
            raise AccountRuleError(detail=_("Нельзя деактивировать самого себя."), code="self_lockout")

        orphans = account_service.deactivate(user=user, actor=request.user)
        return self._result(user=user, orphans=orphans)

    @extend_schema(request=None, responses={200: AccountChangeResultSerializer})
    @action(methods=["POST"], detail=True, url_path="activate", permission_classes=(IsPlatformAdmin,))
    def activate(self, request: Request, pk=None) -> Response:
        """Активирует пользователя; прежние связи с руководителем не восстанавливаются."""
        user = self.get_object()
        account_service.activate(user=user, actor=request.user)
        return self._result(user=user, orphans=[])

    @extend_schema(request=None, responses={200: UserSerializer})
    @action(methods=["POST"], detail=True, url_path="claim", permission_classes=(IsHead,))
    def claim(self, request: Request, pk=None) -> Response:
        """Руководитель забирает свободного КАМа в команду; КАМа другого руководителя забрать нельзя."""
        user = self.get_object()
        try:
            account_service.claim(kam=user, head=request.user, actor=request.user)
        except KamHasHeadError:
            raise ConflictError(detail=_("У КАМа уже есть руководитель."), code="kam_has_head")
        return self._user(user)

    @extend_schema(request=None, responses={200: UserSerializer})
    @action(methods=["POST"], detail=True, url_path="release", permission_classes=(IsHead,))
    def release(self, request: Request, pk=None) -> Response:
        """Руководитель отпускает своего КАМа; КАМ становится свободным."""
        user = self.get_object()
        try:
            account_service.release(kam=user, head=request.user, actor=request.user)
        except NotInTeamError:
            raise ConflictError(detail=_("КАМ не в вашей команде."), code="not_in_team")
        return self._user(user)

    def _user(self, user) -> Response:
        """Пользователь в актуальном состоянии."""
        return Response(
            data=UserSerializer(self.get_queryset().get(pk=user.pk), context=self.get_serializer_context()).data,
            status=status.HTTP_200_OK,
        )

    def _result(self, user, orphans: list) -> Response:
        """Ответ экшена: пользователь в актуальном состоянии и КАМы без руководителя."""
        user = self.get_queryset().get(pk=user.pk)
        return Response(
            data=AccountChangeResultSerializer(
                {"user": user, "orphaned_kams": orphans},
                context=self.get_serializer_context(),
            ).data,
            status=status.HTTP_200_OK,
        )
