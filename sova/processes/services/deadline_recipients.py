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
    лениво и один раз. Ответственный — активный пользователь; руководитель — назначивший КАМа head
    (head_mode=assigned_by) или все активные head.
    """

    def __init__(self, interaction_ids: Iterable[UUID]) -> None:
        self._current = {
            record.interaction_id: record
            for record in Responsible.objects.select_related("manager", "assigned_by__system_role").filter(
                interaction_id__in=set(interaction_ids),
                unassigned_at__isnull=True,
            )
        }
        self._all_heads: list[AbstractBaseUser] | None = None

    def interaction_responsible(self, interaction_id: UUID) -> AbstractBaseUser | None:
        """Активный КАМ взаимодействия или None."""
        record = self._current.get(interaction_id)
        if record is None or not record.manager.is_active:
            return None
        return record.manager

    def recipients(
        self,
        rule: NotifySettings,
        event: str,
        interaction_id: UUID,
        responsible: AbstractBaseUser | None,
    ) -> list[AbstractBaseUser]:
        """Получатели события по флагам правила, без повторов: сначала ответственный, затем руководители."""
        notify_responsible, notify_head = rule.recipient_flags(event)
        users: list[AbstractBaseUser] = []
        if notify_responsible:
            if responsible is not None and responsible.is_active:
                users.append(responsible)
            elif rule.is_fallback_to_head:
                users.extend(self._heads(rule=rule, interaction_id=interaction_id))
        if notify_head:
            users.extend(self._heads(rule=rule, interaction_id=interaction_id))
        return list({user.pk: user for user in users}.values())

    def _heads(self, rule: NotifySettings, interaction_id: UUID) -> list[AbstractBaseUser]:
        """Руководитель по head_mode; если назначивший не подходит — все активные руководители."""
        if rule.head_mode == HeadMode.ASSIGNED_BY:
            record = self._current.get(interaction_id)
            assigned_by = record.assigned_by if record is not None else None
            if (
                assigned_by is not None
                and assigned_by.is_active
                and get_system_role(assigned_by) == SystemRole.HEAD
            ):
                return [assigned_by]
        return self._every_head()

    def _every_head(self) -> list[AbstractBaseUser]:
        """Все активные пользователи с ролью «Руководитель»."""
        if self._all_heads is None:
            self._all_heads = list(
                get_user_model()
                .objects.filter(is_active=True, system_role__role=SystemRole.HEAD)
                .order_by("pk"),
            )
        return self._all_heads
