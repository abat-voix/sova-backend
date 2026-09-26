from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import QuerySet
from rest_framework.exceptions import NotFound

from accounts.models import SystemRole


def get_system_role(user) -> str | None:
    """Возвращает прикладную роль пользователя в СОВА или None, если роли нет."""
    # У обратной связи OneToOne отсутствие записи выглядит как AttributeError
    assignment = getattr(user, "system_role", None)
    return assignment.role if assignment else None


def visible_users(user) -> QuerySet:
    """
    Пользователи, которых видит `user` согласно своей роли в СОВА.

    Руководитель видит КАМов, администратор платформы — всех активных
    пользователей, кроме себя. Остальным роль списка не даёт: запрос к API
    отклоняется разрешением `CanListUsers`, а сам набор пуст.
    """
    user_model = get_user_model()
    role = get_system_role(user)

    if role == SystemRole.PLATFORM_ADMIN:
        queryset = user_model.objects.exclude(
            pk=user.pk
        )
    elif role == SystemRole.HEAD:
        queryset = user_model.objects.filter(system_role__role=SystemRole.KAM)
    else:
        return user_model.objects.none()

    return queryset.filter(is_active=True)


def manageable_users(user) -> QuerySet:
    """Возвращает активных пользователей, которыми может управлять администратор."""
    if get_system_role(user) != SystemRole.PLATFORM_ADMIN:
        return get_user_model().objects.none()

    return (
        get_user_model()
        .objects.filter(is_active=True)
        .exclude(pk=user.pk)
        .select_related("system_role")
    )


@transaction.atomic
def set_system_role(*, actor, target, role: str | None):
    """Назначает или снимает единственную прикладную роль пользователя."""
    if get_system_role(actor) != SystemRole.PLATFORM_ADMIN:
        raise PermissionError("Только администратор платформы может менять роли.")
    if actor.pk == target.pk or not target.is_active:
        raise NotFound("Пользователь недоступен для изменения.")

    from accounts.models import UserRole

    if role is None:
        UserRole.objects.filter(user=target).delete()
    else:
        UserRole.objects.update_or_create(user=target, defaults={"role": role})

    target.refresh_from_db()
    return target
