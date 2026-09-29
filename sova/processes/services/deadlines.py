import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from django.contrib.auth.models import AbstractBaseUser
from django.db.models import Prefetch

from sova.interactions.models import Interaction
from sova.notifications.enum import NotifyEvent, NotifyType
from sova.notifications.models import NotifySettings
from sova.processes.enum import ActionInstanceStatus, StageInstanceStatus, WorkflowInstanceStatus
from sova.processes.models import ActionInstance, StageInstance, WorkflowInstance
from sova.processes.services.deadline_recipients import DeadlineRecipientResolver

logger = logging.getLogger("django")

_INTERACTION_RELATED = ("interaction__organization", "interaction__b2c_client")


@dataclass(frozen=True)
class DeadlineItem:
    """Пункт уведомления: объект, его срок, событие и получатели."""

    notify_type: str
    event: str
    object_id: UUID
    deadline: datetime
    counterparty: str
    workflow_name: str
    stage_name: str = ""
    action_name: str = ""
    recipients: tuple = ()
    # Для ссылки на объект: взаимодействие и процесс, где искать объект
    interaction_id: UUID | None = None
    workflow_instance_id: UUID | None = None


@dataclass(frozen=True)
class _Candidate:
    """Объект со сроком до получателей: ответственный известен только у действия, и то не всегда (пул)."""

    object_id: UUID
    deadline: datetime
    interaction: Interaction
    workflow_instance_id: UUID
    workflow_name: str
    stage_name: str = ""
    action_name: str = ""
    responsible: AbstractBaseUser | None = None


class DeadlineService:
    """
    Сроки действий, этапов и процессов для уведомлений (правила — в спеке уведомлений о сроках).

    Действие: не выполнено, planned_end задан, у WorkflowAction есть default_duration_days, этап в работе,
    не ждёт запуска. Этап: в работе, срок — максимум planned_end действий, хотя бы у одного действия есть
    длительность. Процесс: идёт, срок — started_at + stale_threshold_days. Везде процесс RUNNING,
    взаимодействие активно. Не отправляет и не пишет журнал.
    """

    def collect(self, now: datetime) -> list[DeadlineItem]:
        """Пункты событий overdue и reminder по включённым правилам NotifySettings."""
        rules = NotifySettings.objects.in_bulk(field_name="notify_type")
        loaders: dict[str, Callable[[datetime], list[_Candidate]]] = {
            NotifyType.ACTION_DEADLINE: self._action_candidates,
            NotifyType.STAGE_DEADLINE: self._stage_candidates,
            NotifyType.WORKFLOW_DEADLINE: self._workflow_candidates,
        }
        candidates: list[tuple[NotifySettings, _Candidate]] = []
        for kind, load in loaders.items():
            rule = rules.get(kind)
            if rule is None:
                logger.warning("Нет NotifySettings для «%s» — контроль сроков выключен", kind)
                continue
            if not rule.is_enabled:
                continue
            # Горизонт выборки: всё просроченное плюс окно предупреждения
            horizon = now + timedelta(days=rule.remind_before_days or 0)
            candidates.extend((rule, candidate) for candidate in load(horizon))

        resolver = DeadlineRecipientResolver(interaction_ids=[candidate.interaction.pk for _, candidate in candidates])
        items: list[DeadlineItem] = []
        for rule, candidate in candidates:
            event = self._event(rule=rule, deadline=candidate.deadline, now=now)
            if event is None:
                continue
            # У действия свой ответственный; действие из пула, этап и процесс — все КАМы взаимодействия
            if rule.notify_type == NotifyType.ACTION_DEADLINE and candidate.responsible is not None:
                responsibles = [candidate.responsible]
            else:
                responsibles = resolver.interaction_responsibles(candidate.interaction.pk)
            recipients = resolver.recipients(
                rule=rule,
                event=event,
                interaction_id=candidate.interaction.pk,
                responsibles=responsibles,
            )
            if not recipients:
                continue
            items.append(
                DeadlineItem(
                    notify_type=rule.notify_type,
                    event=event,
                    object_id=candidate.object_id,
                    deadline=candidate.deadline,
                    counterparty=self._counterparty(candidate.interaction),
                    workflow_name=candidate.workflow_name,
                    stage_name=candidate.stage_name,
                    action_name=candidate.action_name,
                    recipients=tuple(recipients),
                    interaction_id=candidate.interaction.pk,
                    workflow_instance_id=candidate.workflow_instance_id,
                ),
            )
        return items

    def _event(self, rule: NotifySettings, deadline: datetime, now: datetime) -> str | None:
        """overdue — срок прошёл; reminder — срок в окне remind_before_days; иначе None."""
        if deadline < now:
            return NotifyEvent.OVERDUE
        if rule.remind_before_days is not None and deadline - timedelta(days=rule.remind_before_days) <= now:
            return NotifyEvent.REMINDER
        return None

    def _counterparty(self, interaction: Interaction) -> str:
        """Организация или B2C-клиент взаимодействия — str(interaction) содержит UUID и для письма не годится."""
        return str(interaction.organization or interaction.b2c_client)

    def _action_candidates(self, horizon: datetime) -> list[_Candidate]:
        """Незавершённые контролируемые действия со сроком до горизонта."""
        instances = (
            ActionInstance.objects.filter(
                planned_end__lte=horizon,
                action__default_duration_days__isnull=False,
                stage_instance__status=StageInstanceStatus.IN_PROGRESS,
                stage_instance__workflow_instance__status=WorkflowInstanceStatus.RUNNING,
                stage_instance__workflow_instance__interaction__is_active=True,
            )
            .exclude(status=ActionInstanceStatus.COMPLETED)
            # Незапущенное trigger-only действие может так и не понадобиться — это не срыв срока
            .exclude(action__is_trigger_only=True, triggered_at__isnull=True)
            .select_related(
                "responsible",
                "stage_instance__stage",
                "stage_instance__workflow_instance__workflow",
                *(f"stage_instance__workflow_instance__{name}" for name in _INTERACTION_RELATED),
            )
        )
        candidates = []
        for instance in instances:
            process = instance.stage_instance.workflow_instance
            candidates.append(
                _Candidate(
                    object_id=instance.pk,
                    deadline=instance.planned_end,
                    interaction=process.interaction,
                    workflow_instance_id=process.pk,
                    workflow_name=str(process.workflow),
                    stage_name=instance.stage_instance.stage.name,
                    action_name=instance.action_name_snapshot,
                    responsible=instance.responsible,
                ),
            )
        return candidates

    def _stage_candidates(self, horizon: datetime) -> list[_Candidate]:
        """Этапы в работе, у которых последнее плановое окончание действий до горизонта."""
        stages = (
            StageInstance.objects.filter(
                status=StageInstanceStatus.IN_PROGRESS,
                workflow_instance__status=WorkflowInstanceStatus.RUNNING,
                workflow_instance__interaction__is_active=True,
            )
            .select_related(
                "stage",
                "workflow_instance__workflow",
                *(f"workflow_instance__{name}" for name in _INTERACTION_RELATED),
            )
            .prefetch_related(
                Prefetch("action_instances", queryset=ActionInstance.objects.select_related("action")),
            )
        )
        candidates = []
        for stage_instance in stages:
            actions = [
                instance
                for instance in stage_instance.action_instances.all()
                if not (instance.action.is_trigger_only and instance.triggered_at is None)
            ]
            # Без единой заданной длительности срок этапа — одни «сутки по умолчанию» планировщика
            if not any(instance.action.default_duration_days is not None for instance in actions):
                continue
            ends = [instance.planned_end for instance in actions if instance.planned_end is not None]
            if not ends or max(ends) > horizon:
                continue
            process = stage_instance.workflow_instance
            candidates.append(
                _Candidate(
                    object_id=stage_instance.pk,
                    deadline=max(ends),
                    interaction=process.interaction,
                    workflow_instance_id=process.pk,
                    workflow_name=str(process.workflow),
                    stage_name=stage_instance.stage.name,
                ),
            )
        return candidates

    def _workflow_candidates(self, horizon: datetime) -> list[_Candidate]:
        """Идущие процессы с SLA, срок которого до горизонта."""
        processes = WorkflowInstance.objects.filter(
            status=WorkflowInstanceStatus.RUNNING,
            workflow__stale_threshold_days__isnull=False,
            interaction__is_active=True,
        ).select_related("workflow", *_INTERACTION_RELATED)
        candidates = []
        for process in processes:
            deadline = process.started_at + timedelta(days=process.workflow.stale_threshold_days)
            if deadline > horizon:
                continue
            candidates.append(
                _Candidate(
                    object_id=process.pk,
                    deadline=deadline,
                    interaction=process.interaction,
                    workflow_instance_id=process.pk,
                    workflow_name=str(process.workflow),
                ),
            )
        return candidates


deadline_service = DeadlineService()
