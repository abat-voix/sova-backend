from collections import defaultdict
from collections.abc import Iterable
from uuid import UUID

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser

from accounts.models import SystemRole
from accounts.services import get_system_role
from sova.interactions.models import Responsible
from sova.notifications.enum import HeadMode
from sova.notifications.models import NotifySettings


class DeadlineRecipientResolver:
    """
    Получатели уведомления о сроке по правилу NotifySettings.

    Активные назначения взаимодействий читаются одним запросом при создании, список всех руководителей —
    лениво и один раз. Ответственные — активные пользователи (у взаимодействия может быть несколько КАМов);
    руководители — назначившие КАМов head (head_mode=assigned_by), руководители КАМов (head_mode=supervisor) или все
    активные head.
    """

    def __init__(self, interaction_ids: Iterable[UUID]) -> None:
        self._current: dict[UUID, list[Responsible]] = defaultdict(list)
        for record in (
            Responsible.objects.select_related(
                "manager__supervision__head__system_role",
                "assigned_by__system_role",
            )
            .filter(interaction_id__in=set(interaction_ids), unassigned_at__isnull=True)
            .order_by("assigned_at", "pk")
        ):
            self._current[record.interaction_id].append(record)
        self._all_heads: list[AbstractBaseUser] | None = None

    def interaction_responsibles(self, interaction_id: UUID) -> list[AbstractBaseUser]:
        """Активные КАМы взаимодействия в порядке назначения."""
        return [record.manager for record in self._current.get(interaction_id, ()) if record.manager.is_active]

    def recipients(
        self,
        rule: NotifySettings,
        event: str,
        interaction_id: UUID,
        responsibles: Iterable[AbstractBaseUser],
    ) -> list[AbstractBaseUser]:
        """Получатели события по флагам правила, без повторов: сначала ответственные, затем руководители."""
        notify_responsible, notify_head = rule.recipient_flags(event)
        users: list[AbstractBaseUser] = []
        if notify_responsible:
            active = [user for user in responsibles if user.is_active]
            if active:
                users.extend(active)
            elif rule.is_fallback_to_head:
                users.extend(self._heads(rule=rule, interaction_id=interaction_id))
        if notify_head:
            users.extend(self._heads(rule=rule, interaction_id=interaction_id))
        return list({user.pk: user for user in users}.values())

    def _heads(self, rule: NotifySettings, interaction_id: UUID) -> list[AbstractBaseUser]:
        """Руководители по head_mode; если ни один не подходит — все активные руководители."""
        records = self._current.get(interaction_id, ())
        if rule.head_mode == HeadMode.ASSIGNED_BY:
            candidates = [record.assigned_by for record in records]
        elif rule.head_mode == HeadMode.SUPERVISOR:
            candidates = [self._supervisor(record.manager) for record in records if record.manager.is_active]
        else:
            candidates = []
        # Роль и активность проверяются здесь: связь или назначение могли устареть
        heads = {
            user.pk: user
            for user in candidates
            if user is not None and user.is_active and get_system_role(user) == SystemRole.HEAD
        }
        return list(heads.values()) or self._every_head()

    @staticmethod
    def _supervisor(manager: AbstractBaseUser) -> AbstractBaseUser | None:
        """Руководитель КАМа из связи `Supervision` или None."""
        supervision = getattr(manager, "supervision", None)
        return supervision.head if supervision is not None else None

    def _every_head(self) -> list[AbstractBaseUser]:
        """Все активные пользователи с ролью «Руководитель»."""
        if self._all_heads is None:
            self._all_heads = list(
                get_user_model()
                .objects.filter(is_active=True, system_role__role=SystemRole.HEAD)
                .order_by("pk"),
            )
        return self._all_heads
