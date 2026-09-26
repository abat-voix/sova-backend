from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from django.db.models import Q, QuerySet

from accounts.models import SystemRole
from accounts.policy import effective_role
from sova.interactions.models import Interaction, Responsible


@dataclass(frozen=True)
class ManagerCandidate:
    """Кандидат в ответственные взаимодействия — строка окна назначения."""

    manager: AbstractBaseUser
    from_registry: bool
    assignable: bool
    is_responsible: bool


def assignable_managers(actor) -> QuerySet:
    """
    Кого `actor` может назначить ответственным.

    Администратор (и superuser) — активных КАМов и руководителей; руководитель — себя, КАМов своей команды и свободных (свободный
    при назначении вступает в команду, см. `ResponsibleService.assign_by`); КАМ — только себя. Роль и активность
    проверяются по текущим данным: связь, устаревшая после изменений в обход сервиса, прав не даёт.
    """
    active = get_user_model().objects.filter(is_active=True)
    role = effective_role(actor)

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
    Кого `actor` может снять с ответственных: администратор (и superuser) — любого, руководитель — себя, свою команду и неактивных
    КАМов (деактивация удаляет связь с командой, и снять уволенного иначе мог бы только администратор).
    """
    users = get_user_model().objects.all()
    role = effective_role(actor)

    if role == SystemRole.PLATFORM_ADMIN:
        return users
    if role == SystemRole.HEAD:
        team_or_inactive = Q(supervision__head=actor) | Q(is_active=False)
        return users.filter(Q(pk=actor.pk) | (Q(system_role__role=SystemRole.KAM) & team_or_inactive))
    return users.none()


def assignment_candidates(interaction: Interaction, actor) -> list[ManagerCandidate]:
    """
    Кандидаты в ответственные для окна назначения: кого `actor` может назначить и КАМы из реестра договоров.

    КАМы из реестра — действующие ответственные договоров взаимодействия, назначенные импортом; подсказка только
    руководителю и администратору (КАМ назначает лишь себя). Они идут первыми и показываются, даже если `actor` не
    может их назначить (например, КАМ чужой команды) — тогда `assignable=False`. Внутри групп — по фамилии и имени.
    """
    active = Responsible.objects.filter(unassigned_at__isnull=True)
    registry_ids: set[int] = set()
    if effective_role(actor) in (SystemRole.HEAD, SystemRole.PLATFORM_ADMIN):
        registry_ids = set(
            active.filter(contract__interaction=interaction, interaction__isnull=True).values_list(
                "manager_id", flat=True
            )
        )
    responsible_ids = set(active.filter(interaction=interaction).values_list("manager_id", flat=True))
    assignable_ids = set(assignable_managers(actor).values_list("pk", flat=True))

    users = get_user_model().objects.filter(pk__in=registry_ids | assignable_ids).order_by("last_name", "first_name", "pk")
    candidates = [
        ManagerCandidate(
            manager=user,
            from_registry=user.pk in registry_ids,
            assignable=user.pk in assignable_ids,
            is_responsible=user.pk in responsible_ids,
        )
        for user in users
    ]
    return sorted(candidates, key=lambda candidate: not candidate.from_registry)
