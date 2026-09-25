from rest_framework.permissions import IsAuthenticated

from accounts.models import SystemRole
from accounts.services import get_system_role


class CanListUsers(IsAuthenticated):
    """Список пользователей доступен руководителю и администратору платформы."""

    message = (
        "Список пользователей доступен руководителю и администратору платформы."
    )
    allowed_roles = frozenset({SystemRole.HEAD, SystemRole.PLATFORM_ADMIN})

    def has_permission(self, request, view) -> bool:
        """Проверяет аутентификацию и прикладную роль пользователя."""
        if not super().has_permission(request, view):
            return False
        return get_system_role(request.user) in self.allowed_roles


class IsPlatformAdmin(IsAuthenticated):
    """Управление пользователями доступно только администратору платформы."""

    message = "Управление пользователями доступно только администратору платформы."

    def has_permission(self, request, view) -> bool:
        """Проверяет аутентификацию и роль администратора платформы."""
        return super().has_permission(request, view) and get_system_role(request.user) == SystemRole.PLATFORM_ADMIN


class IsHead(IsAuthenticated):
    """Вести свою команду может только руководитель."""

    message = "Команду ведёт только руководитель."

    def has_permission(self, request, view) -> bool:
        """Проверяет аутентификацию и роль руководителя."""
        return super().has_permission(request, view) and get_system_role(request.user) == SystemRole.HEAD
