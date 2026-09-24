from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from sova.interactions.exceptions import NoActiveResponsibleError
from sova.interactions.models import Interaction, Responsible
from sova.notifications.enum import NotifyType
from sova.notifications.services.event_notification import event_notification_service
from sova.notifications.services.links import interaction_link
from sova.notifications.services.message import Message
from sova.processes.enum import ActionInstanceStatus
from sova.processes.models import ActionInstance


class ResponsibleService:
    """
    Назначение и снятие ответственного менеджера (КАМ) на взаимодействие.

    Responsible — журнал с историей: запись никогда не перезаписывается, смена
    ответственного закрывает действующую запись (`unassigned_at`) и создаёт новую.
    Одна действующая запись на взаимодействие гарантируется ограничением БД
    `one_active_responsible_per_interaction`; блокировка строки взаимодействия
    сериализует параллельные назначения, чтобы вместо ошибки ограничения второй
    запрос дождался первого. При смене менеджера открытые действия прежнего
    менеджера передаются новому, при снятии без замены — остаются без ответственного,
    а завершённые исполнения остаются в истории. Новый КАМ получает уведомление «Назначение КАМа» по настройкам
    этого типа.
    """

    @transaction.atomic
    def assign(
        self,
        interaction: Interaction,
        manager: AbstractBaseUser,
        assigned_by: AbstractBaseUser | None,
    ) -> tuple[Responsible, bool]:
        """
        Назначает менеджера ответственным за взаимодействие.

        Возвращает пару (запись, создана_ли_новая). Если менеджер уже
        ответственный, история не меняется и возвращается действующая запись.
        """
        Interaction.objects.select_for_update().get(pk=interaction.pk)
        current = self._get_current(interaction=interaction)

        if current is not None and current.manager_id == manager.pk:
            return current, False
        previous_manager_id = current.manager_id if current is not None else None
        if current is not None:
            self._close(responsible=current)

        responsible = Responsible.objects.create(
            interaction=interaction,
            manager=manager,
            assigned_by=assigned_by,
        )
        transferred = self._sync_open_action_instances(
            interaction=interaction,
            previous_manager_id=previous_manager_id,
            manager=manager,
        )
        self._notify_assigned(
            interaction=interaction,
            manager=manager,
            assigned_by=assigned_by,
            transferred=transferred,
        )
        return responsible, True

    @transaction.atomic
    def unassign(self, interaction: Interaction) -> Responsible:
        """Снимает действующего ответственного, не назначая нового; его открытые действия остаются без ответственного."""
        Interaction.objects.select_for_update().get(pk=interaction.pk)
        current = self._get_current(interaction=interaction)
        if current is None:
            raise NoActiveResponsibleError
        self._close(responsible=current)
        self._release_open_action_instances(interaction=interaction, manager_id=current.manager_id)
        return current

    def _get_current(self, interaction: Interaction) -> Responsible | None:
        """Возвращает действующее назначение взаимодействия."""
        return Responsible.objects.filter(
            interaction=interaction,
            unassigned_at__isnull=True,
        ).first()

    def _close(self, responsible: Responsible) -> None:
        """Закрывает назначение текущим моментом."""
        responsible.unassigned_at = timezone.now()
        responsible.save(update_fields=["unassigned_at"])

    def _sync_open_action_instances(
        self,
        interaction: Interaction,
        previous_manager_id: int | None,
        manager: AbstractBaseUser,
    ) -> int:
        """Передаёт открытые задачи новому ответственному, сохраняя историю завершённых."""
        actions = ActionInstance.objects.filter(
            stage_instance__workflow_instance__interaction=interaction,
            status__in=(ActionInstanceStatus.PENDING, ActionInstanceStatus.IN_PROGRESS),
        )
        if previous_manager_id is None:
            actions = actions.filter(responsible__isnull=True)
        else:
            actions = actions.filter(
                Q(responsible_id=previous_manager_id) | Q(responsible__isnull=True),
            )
        return actions.update(responsible=manager)

    def _notify_assigned(
        self,
        interaction: Interaction,
        manager: AbstractBaseUser,
        assigned_by: AbstractBaseUser | None,
        transferred: int,
    ) -> None:
        """Уведомляет нового КАМа; назначившему самого себя не отправляется — его отсекает actor."""
        text = f"Вас назначили КАМом — {interaction.university or interaction.b2c_client}"
        if transferred:
            text += f"\n\nПередано открытых задач: {transferred}"
        event_notification_service.notify(
            notify_type=NotifyType.KAM_ASSIGNED,
            message=Message(text=text, link=interaction_link(interaction_id=interaction.pk)),
            responsible=manager,
            head=assigned_by,
            actor=assigned_by,
        )

    def _release_open_action_instances(self, interaction: Interaction, manager_id: int) -> int:
        """Снимает снятого менеджера с открытых задач взаимодействия; завершённые исполнения остаются в истории."""
        return ActionInstance.objects.filter(
            stage_instance__workflow_instance__interaction=interaction,
            status__in=(ActionInstanceStatus.PENDING, ActionInstanceStatus.IN_PROGRESS),
            responsible_id=manager_id,
        ).update(responsible=None)


responsible_service = ResponsibleService()
