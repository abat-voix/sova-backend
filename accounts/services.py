from django.contrib.auth import get_user_model
from django.db.models import QuerySet

from accounts.models import SystemRole


def get_system_role(user) -> str | None:
    """Возвращает прикладную роль пользователя в СОВА или None, если роли нет."""
    # У обратной связи OneToOne отсутствие записи выглядит как AttributeError
    assignment = getattr(user, "system_role", None)
    return assignment.role if assignment else None


def visible_users(user) -> QuerySet:
    """
    Пользователи, которых видит `user` согласно своей роли в СОВА.

    Руководитель видит КАМов, администратор платформы — всех, кроме других
    администраторов платформы. Остальным роль списка не даёт: запрос к API
    отклоняется разрешением `CanListUsers`, а сам набор пуст.
    """
    user_model = get_user_model()
    role = get_system_role(user)

    if role == SystemRole.PLATFORM_ADMIN:
        queryset = user_model.objects.exclude(
            system_role__role=SystemRole.PLATFORM_ADMIN
        )
    elif role == SystemRole.HEAD:
        queryset = user_model.objects.filter(system_role__role=SystemRole.KAM)
    else:
        return user_model.objects.none()

    return queryset.filter(is_active=True)
