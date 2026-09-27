from rest_framework.permissions import IsAuthenticated

from accounts.models import SystemRole
from accounts.policy import Action, can, effective_role
from accounts.services import get_system_role


class PolicyPermission(IsAuthenticated):
    """
    Права API по политике `accounts.policy` — разрешение по умолчанию для всех view.

    View, переведённый на политику, объявляет `policy_actions`: код операции для каждого своего действия (`list`,
    `retrieve`, `create`, имя `@action`); действию с несколькими HTTP-методами — словарь `{метод: код}`. Действие
    без кода запрещено. Видимость конкретной записи обеспечивает `get_queryset` view: чужая запись — 404, запрещённая
    операция над видимой — 403.

    View без `policy_actions` на политику ещё не переведён: он доступен пользователю с прикладной ролью, кроме
    наблюдателя. Пользователь без роли бизнес API не получает.
    """

    message = "Недостаточно прав для этой операции."

    def has_permission(self, request, view) -> bool:
        """Проверяет аутентификацию и право на операцию текущего действия view."""
        if not super().has_permission(request, view):
            return False
        policy_action = getattr(view, "policy_action", None)
        if policy_action is not None:
            return can(request.user, policy_action)

        policy_actions = getattr(view, "policy_actions", None)
        if policy_actions is None:
            return effective_role(request.user) is not None and get_system_role(request.user) != SystemRole.OBSERVER
        if getattr(view, "action_map", None) is not None and view.action is None:
            # У ViewSet нет действия для этого HTTP-метода: DRF ответит 405 и ничего не выполнит.
            # `ViewSetMixin` не импортируется: модуль грузится из настроек DRF во время импорта самого DRF
            return True
        action = self.get_policy_action(request=request, view=view, policy_actions=policy_actions)
        return action is not None and can(request.user, action)

    @staticmethod
    def get_policy_action(request, view, policy_actions: dict) -> str | None:
        """Код операции текущего запроса по `policy_actions` view."""
        # OPTIONS описывает эндпоинт, а не меняет данные — требует того же права, что и список
        view_action = getattr(view, "action", None)
        if view_action == "metadata":
            view_action = "list"
        action = policy_actions.get(view_action)
        if action is None and view_action is None:
            action = policy_actions.get(request.method)
        if isinstance(action, dict):
            method = "GET" if request.method == "HEAD" else request.method
            return action.get(method)
        return action


class CanListUsers(IsAuthenticated):
    """Список пользователей доступен руководителю и администратору платформы."""

    message = (
        "Список пользователей доступен руководителю и администратору платформы."
    )
    def has_permission(self, request, view) -> bool:
        """Проверяет аутентификацию и прикладную роль пользователя."""
        if not super().has_permission(request, view):
            return False
        return can(request.user, Action.USERS_READ)


class IsPlatformAdmin(IsAuthenticated):
    """Управление пользователями доступно только администратору платформы."""

    message = "Управление пользователями доступно только администратору платформы."

    def has_permission(self, request, view) -> bool:
        """Проверяет аутентификацию и роль администратора платформы."""
        return super().has_permission(request, view) and can(request.user, Action.USERS_MANAGE)


class IsHead(IsAuthenticated):
    """Забирать и отпускать КАМов может только пользователь с ролью руководителя."""

    message = "Команду ведёт только руководитель."

    def has_permission(self, request, view) -> bool:
        """Проверяет аутентификацию и прикладную роль руководителя."""
        return super().has_permission(request, view) and get_system_role(request.user) == SystemRole.HEAD
