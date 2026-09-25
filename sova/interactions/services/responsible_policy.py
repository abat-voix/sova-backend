from django.contrib.auth import get_user_model
from django.db.models import Q, QuerySet

from accounts.models import SystemRole
from accounts.services import get_system_role


def assignable_managers(actor) -> QuerySet:
    """
    Кого `actor` может назначить ответственным.

    Администратор — активных КАМов и руководителей; руководитель — себя, КАМов своей команды и свободных (свободный
    при назначении вступает в команду, см. `ResponsibleService.assign_by`); КАМ — только себя. Роль и активность
    проверяются по текущим данным: связь, устаревшая после изменений в обход сервиса, прав не даёт.
    """
    active = get_user_model().objects.filter(is_active=True)
    role = get_system_role(actor)

    if role == SystemRole.PLATFORM_ADMIN:
        return active.filter(system_role__role__in=(SystemRole.KAM, SystemRole.HEAD))
    if role == SystemRole.HEAD:
        team_or_free = Q(supervision__head=actor) | Q(supervision__isnull=True)
        return active.filter(Q(pk=actor.pk) | (Q(system_role__role=SystemRole.KAM) & team_or_free))
    if role == SystemRole.KAM:
        return active.filter(pk=actor.pk)
    return active.none()


def removable_managers(actor) -> QuerySet:
    """
    Кого `actor` может снять с ответственных: администратор — любого, руководитель — себя, свою команду и неактивных
    КАМов (деактивация удаляет связь с командой, и снять уволенного иначе мог бы только администратор).
    """
    users = get_user_model().objects.all()
    role = get_system_role(actor)

    if role == SystemRole.PLATFORM_ADMIN:
        return users
    if role == SystemRole.HEAD:
        team_or_inactive = Q(supervision__head=actor) | Q(is_active=False)
        return users.filter(Q(pk=actor.pk) | (Q(system_role__role=SystemRole.KAM) & team_or_inactive))
    return users.none()
