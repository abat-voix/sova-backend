from rest_framework.permissions import IsAuthenticated

from accounts.models import SystemRole
from accounts.services import get_system_role


class CanManageIntegrations(IsAuthenticated):
    message = "Управление интеграциями доступно только администратору."

    def has_permission(self, request, view):
        return super().has_permission(request, view) and (
            request.user.is_staff
            or get_system_role(request.user) == SystemRole.PLATFORM_ADMIN
        )
