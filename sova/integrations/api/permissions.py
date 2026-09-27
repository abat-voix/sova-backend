from rest_framework.permissions import IsAuthenticated

from accounts.policy import Action, can


class CanManageIntegrations(IsAuthenticated):
    message = "Управление интеграциями доступно только администратору."

    def has_permission(self, request, view):
        return super().has_permission(request, view) and can(request.user, Action.INTEGRATIONS_MANAGE)
