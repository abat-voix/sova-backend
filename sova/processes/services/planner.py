from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

from sova.processes.enum import ActionInstanceStatus
from sova.processes.models import ActionInstance, StageInstance, WorkflowInstance
from sova.workflows.models import ActionDependency, ActionTransition

# Длительность действия, у которого она не задана в шаблоне
_DEFAULT_DURATION = timedelta(days=1)


@dataclass
class _Span:
    """Посчитанный интервал этапа или действия."""

    start: datetime
    end: datetime


class _Calculation:
    """
    Один расчёт плана. Держит промежуточные результаты, поэтому сервис-синглтон состояния не хранит.

    Интервалы считаются по требованию и запоминаются: графы этапов и действий обходятся вглубь,
    а `visiting` не даёт зациклиться на возвратной связи.
    """

    def __init__(
        self,
        process: WorkflowInstance,
        stage_instances: list[StageInstance],
        predecessors: dict,
        origin: datetime,
    ) -> None:
        self.process = process
        self.stage_instances = stage_instances
        self.predecessors = predecessors
        self.origin = origin
        self.actions: dict = {}
        self.dependencies: dict = {}
        self.triggers: dict = {}
        self.stage_spans: dict = {}
        self.action_spans: dict = {}
        self.changed: list[ActionInstance] = []

    def execute(self) -> None:
        """Считает план всего процесса и сохраняет то, что раньше было пустым."""
        self.actions = self._load_actions()
        self.dependencies = self._load_dependencies()
        self.triggers = self._load_triggers()
        for item in self.stage_instances:
            self._stage_span(item=item, visiting=frozenset())
        if self.changed:
            ActionInstance.objects.bulk_update(self.changed, ["planned_start", "planned_end"])

    def _stage_span(self, item: StageInstance, visiting: frozenset) -> _Span | None:
        """Интервал этапа: от конца последнего предшественника до конца последнего его действия."""
        cached = self.stage_spans.get(item.pk)
        if cached is not None:
            return cached
        if item.pk in visiting:
            # Возвратная связь: предшественник, до которого мы уже спускаемся, в расчёт не идёт
            return None
        visiting = visiting | {item.pk}
        ends = []
        for source in self.predecessors.get(item.pk, ()):
            span = self._stage_span(item=source, visiting=visiting)
            if span is not None:
                ends.append(span.end)
        start = max(ends) if ends else self.origin
        span = _Span(start=start, end=self._plan_actions(item=item, start=start))
        self.stage_spans[item.pk] = span
        return span

    def _plan_actions(self, item: StageInstance, start: datetime) -> datetime:
        """Планирует действия этапа и возвращает конец этапа: максимум по действиям."""
        instances = self.actions.get(item.pk, {})
        ends = []
        for instance in instances.values():
            span = self._action_span(
                instance=instance,
                instances=instances,
                stage_start=start,
                visiting=frozenset(),
            )
            if span is not None:
                ends.append(span.end)
        return max(ends) if ends else start

    def _action_span(
        self,
        instance: ActionInstance,
        instances: dict,
        stage_start: datetime,
        visiting: frozenset,
    ) -> _Span | None:
        """
        Интервал действия.

        Уже проставленные даты не пересчитываются: базовый план неизменен, и однажды посчитанное
        действие служит опорой для наследников — в том числе для группы, заведённой после старта.
        """
        cached = self.action_spans.get(instance.pk)
        if cached is not None:
            return cached
        if instance.pk in visiting:
            return None
        visiting = visiting | {instance.pk}
        start = instance.planned_start or self._action_start(
            instance=instance,
            instances=instances,
            stage_start=stage_start,
            visiting=visiting,
        )
        end = instance.planned_end or start + self._duration(instance=instance)
        span = _Span(start=start, end=end)
        self.action_spans[instance.pk] = span
        if instance.status != ActionInstanceStatus.COMPLETED and (
            instance.planned_start is None or instance.planned_end is None
        ):
            instance.planned_start = start
            instance.planned_end = end
            self.changed.append(instance)
        return span

    def _action_start(
        self,
        instance: ActionInstance,
        instances: dict,
        stage_start: datetime,
        visiting: frozenset,
    ) -> datetime:
        """Начало действия: конец последнего предусловия, иначе начало этапа."""
        sources = list(self.dependencies.get(instance.action_id, ()))
        if instance.action.is_trigger_only:
            sources.extend(self.triggers.get(instance.action_id, ()))
        ends = []
        for source_id in sources:
            source = instances.get(source_id)
            if source is None:
                # Предусловие из другого этапа движок игнорирует — планировщик тоже
                continue
            span = self._action_span(
                instance=source,
                instances=instances,
                stage_start=stage_start,
                visiting=visiting,
            )
            if span is not None:
                ends.append(span.end)
        return max(ends) if ends else stage_start

    def _duration(self, instance: ActionInstance) -> timedelta:
        """Плановая длительность действия; без неё в шаблоне — сутки."""
        days = instance.action.default_duration_days
        return _DEFAULT_DURATION if days is None else timedelta(days=days)

    def _load_actions(self) -> dict:
        """Последнее исполнение каждого активного действия: экземпляр этапа → действие → экземпляр."""
        latest: dict = defaultdict(dict)
        instances = (
            ActionInstance.objects.filter(stage_instance__in=self.stage_instances, action__is_active=True)
            .select_related("action")
            .order_by("stage_instance_id", "action_id", "execution_no")
        )
        for instance in instances:
            latest[instance.stage_instance_id][instance.action_id] = instance
        return latest

    def _load_dependencies(self) -> dict:
        """Активные зависимости действий workflow: действие → действия, которые оно ждёт."""
        dependencies: dict = defaultdict(list)
        for action_id, depends_on_id in ActionDependency.objects.filter(
            is_active=True,
            action__is_active=True,
            action__stage__workflow_id=self.process.workflow_id,
            depends_on_action__is_active=True,
        ).values_list("action_id", "depends_on_action_id"):
            dependencies[action_id].append(depends_on_id)
        return dependencies

    def _load_triggers(self) -> dict:
        """Активные переходы workflow: целевое действие → действия, чей исход его запускает."""
        triggers: dict = defaultdict(list)
        for target_id, source_id in ActionTransition.objects.filter(
            is_active=True,
            target_action__is_active=True,
            target_action__stage__workflow_id=self.process.workflow_id,
        ).values_list("target_action_id", "outcome__action_id"):
            triggers[target_id].append(source_id)
        return triggers


class WorkflowPlannerService:
    """
    Плановые даты действий процесса.

    Считает `planned_start` и `planned_end` по графу этапов (`StageTransition`), зависимостей
    внутри этапа (`ActionDependency`) и переходов по исходам (`ActionTransition`). Правила описаны
    в `docs/specs/2026-09-21-planned-dates-design.md`. Коротко:
    - этап начинается в конце последнего предшественника, а без предшественников — в `origin`;
      заканчивается в конце последнего своего действия;
    - действие начинается в конце последнего предусловия, а без предусловий — вместе с этапом;
      длится `default_duration_days`, по умолчанию сутки;
    - действие «только по переходу» ждёт конца действия-источника внутри своего этапа.

    Пишет только туда, где дат ещё нет и действие не выполнено, поэтому вызов идемпотентен,
    а однажды посчитанный базовый план не двигается.

    О правилах продвижения процесса не знает: движок передаёт готовые экземпляры этапов и их
    предшественников, а формулы живут здесь.
    """

    def plan(
        self,
        process: WorkflowInstance,
        stage_instances: list[StageInstance],
        predecessors: dict,
        origin: datetime,
    ) -> None:
        """Проставляет плановые даты действиям процесса, у которых их ещё нет."""
        _Calculation(
            process=process,
            stage_instances=stage_instances,
            predecessors=predecessors,
            origin=origin,
        ).execute()


workflow_planner_service = WorkflowPlannerService()
