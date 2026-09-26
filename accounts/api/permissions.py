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
    """Разрешает изменение ролей только администратору платформы."""

    message = "Изменять роли может только администратор платформы."

    def has_permission(self, request, view) -> bool:
        if not super().has_permission(request, view):
            return False
        return get_system_role(request.user) == SystemRole.PLATFORM_ADMIN
