from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from django.contrib.auth.models import AbstractBaseUser
from django.db import IntegrityError, transaction
from django.utils import timezone

from sova.interactions.models import (
    Interaction,
    InteractionDirection,
    InteractionProduct,
    InteractionProgram,
    Responsible,
)
from sova.processes.enum import (
    ActionInstanceStatus,
    RollbackMode,
    StageInstanceContextType,
    StageInstanceStatus,
    WorkflowInstanceStatus,
)
from sova.processes.exceptions import InvalidStateError, RuleViolationError
from sova.processes.models import (
    ActionAttachment,
    ActionInstance,
    ActionResult,
    ActionRollback,
    StageInstance,
    StageRollback,
    WorkflowInstance,
)
from sova.processes.services.planner import workflow_planner_service
from sova.processes.schemas import ActionRollbackOutcome, EngineOutcome, RollbackOutcome
from sova.workflows.enum import Audience
from sova.workflows.models import (
    ActionDependency,
    ActionOutcome,
    ActionTransition,
    StageTransition,
    Workflow,
    WorkflowAction,
    WorkflowStage,
)

# Модели контекстов этапа: для каждого типа этапа — записи взаимодействия, по одной на этап
_CONTEXT_MODELS = {
    StageInstanceContextType.DIRECTION: InteractionDirection,
    StageInstanceContextType.PROGRAM: InteractionProgram,
    StageInstanceContextType.PRODUCT: InteractionProduct,
}


@dataclass
class _Trace:
    """Что изменилось за одну операцию. Живёт только внутри вызова, поэтому сервис-синглтон состояния не хранит."""

    activated_actions: list[ActionInstance] = field(default_factory=list)
    opened_stages: list[StageInstance] = field(default_factory=list)
    completed_stages: list[StageInstance] = field(default_factory=list)
    is_workflow_completed: bool = False


@dataclass
class _Graph:
    """Определение workflow, нужное для расчёта: активные этапы и активные связи между ними."""

    stages: dict[object, WorkflowStage]
    inbound: dict[object, list[object]]
    outbound: dict[object, list[object]]


@dataclass
class ProcessSnapshot:
    """Состояние процесса для расчёта: определение workflow, экземпляры этапов и действующие контексты."""

    graph: _Graph
    instances: list[StageInstance]
    by_key: dict
    by_stage: dict
    live: dict[str, set[object]]
    interaction_id: object


class WorkflowEngineService:
    """
    Движок workflow: запуск процесса, выполнение действий, автоматическое открытие и закрытие этапов, откат.

    Правила описаны в `docs/plans/02-workflow-rules.md`. Коротко:
    - этап открывается, когда закрыты все этапы, ведущие в него по `StageTransition`; этап без входящих
      связей открывается при старте. Этап программы или продукта существует для каждой активной программы
      или продукта взаимодействия и открывается независимо от остальных;
    - действие стартует, когда открыт его этап и выполнены его зависимости; действие, помеченное
      «только по переходу», ещё и ждёт запуска переходом по исходу другого действия;
    - этап закрывается, когда выполнены все обязательные действия (не запущенное переходом действие не
      считается). Этап без обязательных действий закрывается сразу при открытии. Необязательные действия
      остаются доступными и после закрытия этапа и на состояние этапа и процесса не влияют;
    - процесс завершается, когда закрыты все этапы;
    - откат отменяет этап и возвращает процесс на предыдущий; откат действия отменяет только его последнее
      исполнение, и только пока его этап ещё в работе — иначе сначала нужно откатить сам этап.

    Все публичные операции идут в транзакции и блокируют процесс, чтобы параллельные запросы к одному процессу
    выполнялись по очереди. Состояние операции передаётся в приватные методы объектом `_Trace`, а не хранится
    в сервисе.
    """

    # === ПУБЛИЧНЫЕ МЕТОДЫ ===

    @transaction.atomic
    def start(
        self,
        workflow: Workflow,
        interaction: Interaction,
        started_by: AbstractBaseUser | None = None,
    ) -> WorkflowInstance:
        """
        Запускает процесс workflow для взаимодействия.

        Экземпляры этапов и действий создаются сразу, открываются только этапы без входящих связей.
        """
        self._check_can_start(workflow=workflow, interaction=interaction)
        Interaction.objects.select_for_update().get(pk=interaction.pk)
        if WorkflowInstance.objects.filter(workflow=workflow, interaction=interaction).exists():
            raise InvalidStateError(
                "Этот workflow уже запущен для взаимодействия.",
                code="already_started",
            )
        now = timezone.now()
        try:
            with transaction.atomic():
                process = WorkflowInstance.objects.create(
                    workflow=workflow,
                    interaction=interaction,
                    created_by=started_by,
                    status=WorkflowInstanceStatus.RUNNING,
                )
        except IntegrityError as error:
            raise InvalidStateError(
                "Этот workflow уже запущен для взаимодействия.",
                code="already_started",
            ) from error
        self._advance(process=process, now=now, trace=_Trace(), actor=started_by)
        return process

    @transaction.atomic
    def complete_action(
        self,
        action_instance: ActionInstance,
        outcome: ActionOutcome,
        comment: str = "",
        completed_by: AbstractBaseUser | None = None,
    ) -> EngineOutcome:
        """
        Завершает действие с исходом и двигает процесс.

        Порядок: результат → переходы по исходу → запуск готовых действий этапа → закрытие этапа →
        открытие следующих этапов → завершение процесса. Переходы обрабатываются до проверки закрытия,
        чтобы запущенное ими обязательное действие удержало этап открытым.
        """
        process = self._lock_process(process_id=action_instance.stage_instance.workflow_instance_id)
        instance = ActionInstance.objects.select_related("action", "stage_instance__stage").get(
            pk=action_instance.pk,
        )
        outcome = ActionOutcome.objects.get(pk=outcome.pk)
        self._check_can_complete(instance=instance, outcome=outcome, comment=comment)
        now = timezone.now()
        result = ActionResult.objects.create(
            action_instance=instance,
            outcome=outcome,
            outcome_name_snapshot=outcome.name,
            comment=comment,
            created_by=completed_by,
        )
        instance.status = ActionInstanceStatus.COMPLETED
        instance.actual_end = now
        if instance.responsible_id is None:
            instance.responsible = completed_by
        instance.save(update_fields=["status", "actual_end", "responsible"])
        trace = _Trace()
        stage_instance = instance.stage_instance
        self._follow_transition(stage_instance=stage_instance, outcome=outcome, now=now)
        self._activate_ready(stage_instance=stage_instance, now=now, trace=trace)
        if stage_instance.status == StageInstanceStatus.IN_PROGRESS and self._is_closable(
            stage_instance=stage_instance,
        ):
            self._close_stage(stage_instance=stage_instance, now=now, trace=trace)
        self._advance(process=process, now=now, trace=trace, actor=completed_by)
        return EngineOutcome(
            action_instance=instance,
            result=result,
            activated_actions=trace.activated_actions,
            opened_stages=trace.opened_stages,
            completed_stages=trace.completed_stages,
            is_workflow_completed=trace.is_workflow_completed,
        )

    @transaction.atomic
    def cancel_stage(
        self,
        stage_instance: StageInstance,
        mode: str,
        reason: str,
        cancelled_by: AbstractBaseUser | None = None,
        return_to: StageInstance | None = None,
    ) -> RollbackOutcome:
        """
        Отменяет этап в работе и возвращает процесс на предыдущий этап.

        Отменённый этап и все этапы после этапа возврата снова ждут: их действия выполняются заново, прежние
        результаты остаются в истории. Сам этап возврата открывается заново целиком (`RESTART`) или только
        последним обязательным действием (`LAST_ONLY`). Если предшественников несколько, этап возврата
        выбирает пользователь (`return_to`). Откат пишется в журнал `StageRollback`.
        """
        process = self._lock_process(process_id=stage_instance.workflow_instance_id)
        cancelled = StageInstance.objects.select_related("stage").get(pk=stage_instance.pk)
        if cancelled.status != StageInstanceStatus.IN_PROGRESS:
            raise InvalidStateError("Отменить можно только этап в работе.")
        if not reason.strip():
            raise RuleViolationError("Укажите причину отката.", code="reason_required")
        if mode not in RollbackMode.values:
            raise RuleViolationError("Неизвестный режим отката.", code="invalid_mode")
        graph = self._load_graph(process=process)
        target = self._pick_return_stage(process=process, cancelled=cancelled, return_to=return_to)
        last_action = None
        if mode == RollbackMode.LAST_ONLY:
            last_action = self._last_mandatory_action(stage_instance=target)
            if last_action is None:
                raise RuleViolationError(
                    "В этапе возврата нет выполненных обязательных действий.",
                    code="no_mandatory_action",
                )
        now = timezone.now()
        trace = _Trace()
        reset_stages = self._reset_downstream(process=process, target=target, graph=graph)
        self._return_to_stage(target=target, mode=mode, last_action=last_action, now=now, trace=trace)
        rollback = StageRollback.objects.create(
            workflow_instance=process,
            from_stage_instance=cancelled,
            to_stage_instance=target,
            reason=reason,
            mode=mode,
            created_by=cancelled_by,
        )
        self._advance(process=process, now=now, trace=trace, actor=cancelled_by)
        target.refresh_from_db()
        return RollbackOutcome(rollback=rollback, returned_stage=target, reset_stages=reset_stages)

    @transaction.atomic
    def cancel_action(
        self,
        action_instance: ActionInstance,
        reason: str,
        cancelled_by: AbstractBaseUser | None = None,
    ) -> ActionRollbackOutcome:
        """
        Откатывает выполненное действие: новое исполнение вместо отменённого, прежний результат остаётся в истории.

        Откатить можно только последнее исполнение действия, и только если от него не зависит уже выполненное
        действие того же этапа — цепочку зависимостей откатывают строго в обратном порядке, начиная с последнего
        звена. Этап должен быть в работе: если действие закрыло свой этап, сначала откатывают сам этап (`cancel_stage`).
        Откат пишется в журнал `ActionRollback`.
        """
        process = self._lock_process(process_id=action_instance.stage_instance.workflow_instance_id)
        cancelled = ActionInstance.objects.select_related("action", "stage_instance__stage").get(
            pk=action_instance.pk,
        )
        if cancelled.status != ActionInstanceStatus.COMPLETED:
            raise InvalidStateError("Откатить можно только выполненное действие.")
        stage_instance = cancelled.stage_instance
        latest = self._latest_action_instances(stage_instance=stage_instance)
        if latest.get(cancelled.action_id, cancelled).pk != cancelled.pk:
            raise InvalidStateError("Откатить можно только последнее исполнение действия.")
        if stage_instance.status != StageInstanceStatus.IN_PROGRESS:
            raise InvalidStateError(
                "Откатить действие можно только в этапе в работе. Сначала откатите этап.",
            )
        if not reason.strip():
            raise RuleViolationError("Укажите причину отката.", code="reason_required")
        dependents = self._action_dependents(stage_id=stage_instance.stage_id)
        for dependent_id in dependents.get(cancelled.action_id, ()):
            dependent = latest.get(dependent_id)
            if dependent is not None and dependent.status == ActionInstanceStatus.COMPLETED:
                raise RuleViolationError(
                    "Нельзя откатить: от действия зависит уже выполненное действие.",
                    code="has_completed_dependent",
                )
        now = timezone.now()
        trace = _Trace()
        self._reset_action(instance=cancelled)
        self._activate_ready(stage_instance=stage_instance, now=now, trace=trace)
        target = self._latest_action_instances(stage_instance=stage_instance)[cancelled.action_id]
        rollback = ActionRollback.objects.create(
            workflow_instance=process,
            stage_instance=stage_instance,
            from_action_instance=cancelled,
            to_action_instance=target,
            reason=reason,
            created_by=cancelled_by,
        )
        return ActionRollbackOutcome(rollback=rollback, action_instance=target)

    def snapshot(self, process: WorkflowInstance) -> ProcessSnapshot:
        """Загружает состояние процесса: определение, экземпляры этапов и действующие контексты."""
        instances = list(StageInstance.objects.filter(workflow_instance=process).select_related("stage"))
        by_stage: dict = defaultdict(list)
        for item in instances:
            by_stage[item.stage_id].append(item)
        return ProcessSnapshot(
            graph=self._load_graph(process=process),
            instances=instances,
            by_key={(item.stage_id, item.context_id): item for item in instances},
            by_stage=by_stage,
            live=self._live_contexts(interaction=process.interaction),
            interaction_id=process.interaction_id,
        )

    def return_options(self, snapshot: ProcessSnapshot, stage_instance: StageInstance) -> list[StageInstance]:
        """Экземпляры этапов, на которые можно вернуться при отмене этапа: его предшественники."""
        return self._predecessor_instances(snapshot=snapshot, stage_instance=stage_instance)

    def _predecessor_instances(
        self,
        snapshot: ProcessSnapshot,
        stage_instance: StageInstance,
    ) -> list[StageInstance]:
        """Экземпляры этапов-предшественников: их закрытия ждёт этап и от их конца считается его план."""
        options: list[StageInstance] = []
        for from_id in snapshot.graph.inbound.get(stage_instance.stage_id, ()):
            sources, _ = self._source_instances(
                item=stage_instance,
                from_stage=snapshot.graph.stages[from_id],
                snapshot=snapshot,
            )
            options.extend(sources)
        return options

    # === ПРИВАТНЫЕ МЕТОДЫ: ПРОВЕРКИ ===

    def _check_can_start(self, workflow: Workflow, interaction: Interaction) -> None:
        """Проверяет, что workflow активен, подходит контрагенту взаимодействия и содержит этапы."""
        if not workflow.is_active:
            raise RuleViolationError("Workflow неактивен.", code="workflow_inactive")
        has_counterparty = (
            interaction.university_id is not None
            if workflow.audience == Audience.B2B
            else interaction.b2c_client_id is not None
        )
        if not has_counterparty:
            raise RuleViolationError(
                "Аудитория workflow не соответствует контрагенту взаимодействия.",
                code="audience_mismatch",
            )
        if not WorkflowStage.objects.filter(workflow=workflow, is_active=True).exists():
            raise RuleViolationError("В workflow нет активных этапов.", code="empty_workflow")

    def _check_can_complete(self, instance: ActionInstance, outcome: ActionOutcome, comment: str) -> None:
        """Проверяет состояние действия и правила исхода: принадлежность, активность, комментарий, вложение."""
        if instance.status != ActionInstanceStatus.IN_PROGRESS:
            raise InvalidStateError("Завершить можно только действие в работе.")
        if outcome.action_id != instance.action_id:
            raise RuleViolationError("Исход относится к другому действию.", code="outcome_mismatch")
        if not outcome.is_active:
            raise RuleViolationError("Исход неактивен.", code="outcome_inactive")
        if outcome.is_comment_required and not comment.strip():
            raise RuleViolationError("Для этого исхода нужен комментарий.", code="is_comment_required")
        if outcome.is_attachment_required and not ActionAttachment.objects.filter(action_instance=instance).exists():
            raise RuleViolationError("Для этого исхода нужно приложить файл.", code="is_attachment_required")

    # === ПРИВАТНЫЕ МЕТОДЫ: ПРОДВИЖЕНИЕ ПРОЦЕССА ===

    def _lock_process(self, process_id: object) -> WorkflowInstance:
        """Блокирует процесс на время операции и возвращает его актуальное состояние."""
        return WorkflowInstance.objects.select_for_update().select_related("interaction").get(pk=process_id)

    def _advance(
        self,
        process: WorkflowInstance,
        now: datetime,
        trace: _Trace,
        actor: AbstractBaseUser | None,
    ) -> None:
        """Открывает всё, что можно открыть, планирует даты и завершает процесс. Завершённый не трогает."""
        if process.status != WorkflowInstanceStatus.RUNNING:
            return
        self._release(process=process, now=now, trace=trace, actor=actor)
        self._plan(process=process, now=now)
        self._finalize_workflow(process=process, now=now, trace=trace)

    def _plan(self, process: WorkflowInstance, now: datetime) -> None:
        """
        Проставляет плановые даты действиям, у которых их ещё нет.

        Одна точка на все операции: при старте планируется весь процесс, позже — только новое,
        то есть этапы добавленной программы или продукта и действия, у которых откат обнулил план.
        """
        snapshot = self.snapshot(process=process)
        relevant = [item for item in snapshot.instances if self._is_relevant(item, snapshot.graph, snapshot.live)]
        workflow_planner_service.plan(
            process=process,
            stage_instances=relevant,
            predecessors={
                item.pk: self._predecessor_instances(snapshot=snapshot, stage_instance=item) for item in relevant
            },
            origin=now,
        )

    def _release(
        self,
        process: WorkflowInstance,
        now: datetime,
        trace: _Trace,
        actor: AbstractBaseUser | None,
    ) -> None:
        """
        Открывает ожидающие этапы, у которых закрыты все предшественники, пока есть что открывать.

        Перед каждым проходом создаёт недостающие экземпляры: программа или продукт, добавленные после старта,
        получают свой этап. Этап, закрывшийся сразу при открытии, может открыть следующие — поэтому цикл.
        """
        while True:
            self._materialize(process=process, now=now, actor=actor)
            snapshot = self.snapshot(process=process)
            opened_any = False
            for item in snapshot.instances:
                if item.status != StageInstanceStatus.PENDING:
                    continue
                if not self._is_relevant(item, snapshot.graph, snapshot.live):
                    continue
                if not self._predecessors_done(item=item, snapshot=snapshot):
                    continue
                self._open_stage(stage_instance=item, now=now, trace=trace)
                opened_any = True
            if not opened_any:
                return

    def _open_stage(self, stage_instance: StageInstance, now: datetime, trace: _Trace) -> None:
        """Открывает этап, запускает готовые действия и сразу закрывает этап, если обязательных действий нет."""
        stage_instance.status = StageInstanceStatus.IN_PROGRESS
        stage_instance.started_at = now
        stage_instance.save(update_fields=["status", "started_at"])
        trace.opened_stages.append(stage_instance)
        self._activate_ready(stage_instance=stage_instance, now=now, trace=trace)
        if self._is_closable(stage_instance=stage_instance):
            self._close_stage(stage_instance=stage_instance, now=now, trace=trace)

    def _close_stage(self, stage_instance: StageInstance, now: datetime, trace: _Trace) -> None:
        """Закрывает этап."""
        stage_instance.status = StageInstanceStatus.COMPLETED
        stage_instance.completed_at = now
        stage_instance.save(update_fields=["status", "completed_at"])
        trace.completed_stages.append(stage_instance)

    def _finalize_workflow(self, process: WorkflowInstance, now: datetime, trace: _Trace) -> None:
        """Завершает процесс, если все значимые этапы закрыты."""
        graph = self._load_graph(process=process)
        live = self._live_contexts(interaction=process.interaction)
        unfinished = [
            item
            for item in StageInstance.objects.filter(workflow_instance=process)
            if item.status != StageInstanceStatus.COMPLETED and self._is_relevant(item, graph, live)
        ]
        if unfinished:
            return
        process.status = WorkflowInstanceStatus.COMPLETED
        process.completed_at = now
        process.save(update_fields=["status", "completed_at"])
        trace.is_workflow_completed = True

    # === ПРИВАТНЫЕ МЕТОДЫ: ДЕЙСТВИЯ ===

    def _activate_ready(self, stage_instance: StageInstance, now: datetime, trace: _Trace) -> None:
        """
        Запускает ожидающие действия открытого этапа, у которых выполнены зависимости.

        Действие «только по переходу» ждёт ещё и запуска. Закрытый этап тоже обслуживается: необязательное
        действие, ждущее другое необязательное, стартует и после закрытия этапа. Ожидающий этап не трогается.
        """
        if stage_instance.status == StageInstanceStatus.PENDING:
            return
        latest = self._latest_action_instances(stage_instance=stage_instance)
        dependencies = self._action_dependencies(stage_id=stage_instance.stage_id)
        for instance in latest.values():
            action = instance.action
            if instance.status != ActionInstanceStatus.PENDING or not action.is_active:
                continue
            if action.is_trigger_only and instance.triggered_at is None:
                continue
            prerequisites = [latest[item] for item in dependencies.get(action.pk, ()) if item in latest]
            if any(item.status != ActionInstanceStatus.COMPLETED for item in prerequisites):
                continue
            instance.status = ActionInstanceStatus.IN_PROGRESS
            instance.actual_start = now
            # Плановые даты ставит планировщик при старте процесса: активация не должна затирать
            # базовый план моментом, когда до действия дошла очередь
            instance.save(update_fields=["status", "actual_start"])
            trace.activated_actions.append(instance)

    def _is_closable(self, stage_instance: StageInstance) -> bool:
        """
        Можно ли закрыть этап: не осталось обязательных невыполненных действий.

        Обязательное действие, которое запускается только переходом и ещё не запущено, этап не держит.
        """
        for instance in self._latest_action_instances(stage_instance=stage_instance).values():
            action = instance.action
            if not action.is_active or action.is_optional:
                continue
            if instance.status == ActionInstanceStatus.COMPLETED:
                continue
            if (
                action.is_trigger_only
                and instance.status == ActionInstanceStatus.PENDING
                and instance.triggered_at is None
            ):
                continue
            return False
        return True

    def _follow_transition(self, stage_instance: StageInstance, outcome: ActionOutcome, now: datetime) -> None:
        """Запускает целевое действие активного перехода исхода. Цель из другого этапа игнорируется."""
        transition = (
            ActionTransition.objects.select_related("target_action").filter(outcome=outcome, is_active=True).first()
        )
        if transition is None:
            return
        target = transition.target_action
        if not target.is_active or target.stage_id != stage_instance.stage_id:
            return
        latest = self._latest_action_instances(stage_instance=stage_instance).get(target.pk)
        if latest is None:
            return
        if latest.status == ActionInstanceStatus.COMPLETED:
            # Повтор: новое исполнение, прежнее с результатом остаётся в истории
            ActionInstance.objects.create(
                stage_instance=stage_instance,
                action=target,
                action_name_snapshot=target.name,
                status=ActionInstanceStatus.PENDING,
                execution_no=latest.execution_no + 1,
                responsible=latest.responsible,
                triggered_at=now,
            )
        elif latest.status == ActionInstanceStatus.PENDING and latest.triggered_at is None:
            latest.triggered_at = now
            latest.save(update_fields=["triggered_at"])

    def _latest_action_instances(self, stage_instance: StageInstance) -> dict[object, ActionInstance]:
        """Последнее исполнение каждого действия этапа: действие → экземпляр с наибольшим номером исполнения."""
        instances = (
            ActionInstance.objects.filter(stage_instance=stage_instance)
            .select_related("action")
            .order_by("action_id", "execution_no")
        )
        return {item.action_id: item for item in instances}

    def _action_dependencies(self, stage_id: object) -> dict[object, list[object]]:
        """Активные зависимости действий этапа: действие → действия, которые оно ждёт."""
        dependencies: dict = defaultdict(list)
        for action_id, depends_on_id in ActionDependency.objects.filter(
            is_active=True,
            action__stage_id=stage_id,
            depends_on_action__is_active=True,
        ).values_list("action_id", "depends_on_action_id"):
            dependencies[action_id].append(depends_on_id)
        return dependencies

    def _action_dependents(self, stage_id: object) -> dict[object, list[object]]:
        """Активные зависимости действий этапа: действие → действия, которые от него зависят."""
        dependents: dict = defaultdict(list)
        for action_id, depends_on_id in ActionDependency.objects.filter(
            is_active=True,
            action__stage_id=stage_id,
            depends_on_action__is_active=True,
        ).values_list("action_id", "depends_on_action_id"):
            dependents[depends_on_id].append(action_id)
        return dependents

    # === ПРИВАТНЫЕ МЕТОДЫ: ЭТАПЫ И КОНТЕКСТЫ ===

    def _load_graph(self, process: WorkflowInstance) -> _Graph:
        """Загружает активные этапы workflow и активные связи между ними."""
        stages = {
            stage.pk: stage for stage in WorkflowStage.objects.filter(workflow_id=process.workflow_id, is_active=True)
        }
        inbound: dict = defaultdict(list)
        outbound: dict = defaultdict(list)
        for from_id, to_id in StageTransition.objects.filter(
            is_active=True,
            from_stage__is_active=True,
            to_stage__is_active=True,
            from_stage__workflow_id=process.workflow_id,
        ).values_list("from_stage_id", "to_stage_id"):
            inbound[to_id].append(from_id)
            outbound[from_id].append(to_id)
        return _Graph(stages=stages, inbound=inbound, outbound=outbound)

    def _context_ids(self, interaction: Interaction, context_type: str) -> list[object]:
        """Id контекстов этапа: взаимодействие целиком либо его активные направления, программы или продукты."""
        if context_type == StageInstanceContextType.INTERACTION:
            return [interaction.pk]
        return list(
            _CONTEXT_MODELS[context_type]
            .objects.filter(interaction=interaction, is_active=True)
            .values_list("pk", flat=True),
        )

    def _live_contexts(self, interaction: Interaction) -> dict[str, set[object]]:
        """Действующие контексты взаимодействия по типам этапов."""
        return {
            context_type: set(self._context_ids(interaction=interaction, context_type=context_type))
            for context_type in StageInstanceContextType.values
        }

    def _is_relevant(self, item: StageInstance, graph: _Graph, live: dict[str, set[object]]) -> bool:
        """Значим ли экземпляр этапа: его этап активен, а контекст (продукт, программа) не деактивирован."""
        return item.stage_id in graph.stages and item.context_id in live[item.context_type]

    def _materialize(self, process: WorkflowInstance, now: datetime, actor: AbstractBaseUser | None) -> None:
        """Создаёт недостающие экземпляры этапов и действий: для каждого активного этапа и каждого его контекста."""
        stages = list(WorkflowStage.objects.filter(workflow_id=process.workflow_id, is_active=True))
        existing = set(
            StageInstance.objects.filter(workflow_instance=process).values_list("stage_id", "context_id"),
        )
        actions_by_stage: dict | None = None
        responsible = None
        for stage in stages:
            for context_id in self._context_ids(interaction=process.interaction, context_type=stage.type):
                if (stage.pk, context_id) in existing:
                    continue
                if actions_by_stage is None:
                    actions_by_stage = defaultdict(list)
                    for action in WorkflowAction.objects.filter(stage__workflow_id=process.workflow_id, is_active=True):
                        actions_by_stage[action.stage_id].append(action)
                    responsible = self._current_manager(interaction=process.interaction)
                stage_instance = StageInstance.objects.create(
                    workflow_instance=process,
                    stage=stage,
                    context_type=stage.type,
                    context_id=context_id,
                    status=StageInstanceStatus.PENDING,
                    added_by=actor,
                )
                ActionInstance.objects.bulk_create(
                    [
                        ActionInstance(
                            stage_instance=stage_instance,
                            action=action,
                            action_name_snapshot=action.name,
                            status=ActionInstanceStatus.PENDING,
                            execution_no=1,
                            responsible=responsible,
                        )
                        for action in actions_by_stage[stage.pk]
                    ],
                )

    def _current_manager(self, interaction: Interaction) -> AbstractBaseUser | None:
        """Действующий ответственный менеджер взаимодействия."""
        current = (
            Responsible.objects.select_related("manager")
            .filter(interaction=interaction, unassigned_at__isnull=True)
            .first()
        )
        return current.manager if current is not None else None

    def _source_instances(
        self,
        item: StageInstance,
        from_stage: WorkflowStage,
        snapshot: ProcessSnapshot,
    ) -> tuple[list[StageInstance], bool]:
        """
        Экземпляры этапа-предшественника для экземпляра `item`.

        Предшественник уровня взаимодействия или того же типа — один экземпляр (того же контекста).
        Предшественник другого типа — все его действующие экземпляры. Второй элемент — «единственный ли».
        """
        if from_stage.type == StageInstanceContextType.INTERACTION or from_stage.type == item.context_type:
            is_interaction = from_stage.type == StageInstanceContextType.INTERACTION
            context_id = snapshot.interaction_id if is_interaction else item.context_id
            found = snapshot.by_key.get((from_stage.pk, context_id))
            return ([found] if found is not None else []), True
        return (
            [
                source
                for source in snapshot.by_stage.get(from_stage.pk, [])
                if source.context_id in snapshot.live[source.context_type]
            ],
            False,
        )

    def _predecessors_done(self, item: StageInstance, snapshot: ProcessSnapshot) -> bool:
        """Закрыты ли все предшественники этапа. Этап без входящих связей открывается сразу."""
        for from_id in snapshot.graph.inbound.get(item.stage_id, ()):
            sources, single = self._source_instances(
                item=item,
                from_stage=snapshot.graph.stages[from_id],
                snapshot=snapshot,
            )
            if single and not sources:
                return False
            if any(source.status != StageInstanceStatus.COMPLETED for source in sources):
                return False
        return True

    # === ПРИВАТНЫЕ МЕТОДЫ: ОТКАТ ===

    def _pick_return_stage(
        self,
        process: WorkflowInstance,
        cancelled: StageInstance,
        return_to: StageInstance | None,
    ) -> StageInstance:
        """Определяет этап возврата: единственный предшественник или выбранный пользователем из нескольких."""
        candidates = self.return_options(snapshot=self.snapshot(process=process), stage_instance=cancelled)
        if return_to is not None:
            for candidate in candidates:
                if candidate.pk == return_to.pk:
                    return candidate
            raise RuleViolationError(
                "Этап возврата не является предшественником отменяемого.",
                code="invalid_return_to",
            )
        if not candidates:
            raise RuleViolationError("У этапа нет предшественника, на который можно вернуться.", code="no_predecessor")
        if len(candidates) > 1:
            raise RuleViolationError("Выберите этап, на который вернуться.", code="return_to_required")
        return candidates[0]

    def _last_mandatory_action(self, stage_instance: StageInstance) -> ActionInstance | None:
        """Обязательное действие этапа, выполненное последним по времени, то есть закрывшее этап."""
        candidates = [
            item
            for item in self._latest_action_instances(stage_instance=stage_instance).values()
            if item.action.is_active and not item.action.is_optional and item.status == ActionInstanceStatus.COMPLETED
        ]
        if not candidates:
            return None
        finished_at = dict(
            ActionResult.objects.filter(action_instance__in=candidates).values_list("action_instance_id", "created_at"),
        )
        return max(candidates, key=lambda item: (finished_at.get(item.pk, item.actual_end), item.action.sort_order))

    def _reset_downstream(
        self,
        process: WorkflowInstance,
        target: StageInstance,
        graph: _Graph,
    ) -> list[StageInstance]:
        """Возвращает в ожидание все не ожидающие этапы, идущие после этапа возврата (по всем контекстам)."""
        downstream: set = set()
        pending_ids = list(graph.outbound.get(target.stage_id, ()))
        while pending_ids:
            stage_id = pending_ids.pop()
            if stage_id in downstream:
                continue
            downstream.add(stage_id)
            pending_ids.extend(graph.outbound.get(stage_id, ()))
        reset: list[StageInstance] = []
        for item in StageInstance.objects.filter(workflow_instance=process, stage_id__in=downstream):
            if item.status == StageInstanceStatus.PENDING:
                continue
            self._reset_stage(stage_instance=item)
            reset.append(item)
        return reset

    def _reset_stage(self, stage_instance: StageInstance) -> None:
        """Возвращает этап в ожидание; его действия будут выполняться заново."""
        for instance in self._latest_action_instances(stage_instance=stage_instance).values():
            self._reset_action(instance=instance)
        stage_instance.status = StageInstanceStatus.PENDING
        stage_instance.started_at = None
        stage_instance.completed_at = None
        stage_instance.save(update_fields=["status", "started_at", "completed_at"])

    def _reset_action(self, instance: ActionInstance) -> None:
        """
        Сбрасывает действие, чтобы оно выполнялось заново.

        Выполненное действие получает новое исполнение — прежнее с результатом остаётся в истории.
        Незавершённое сбрасывается на месте: результата у него нет, терять нечего.
        """
        if instance.status == ActionInstanceStatus.COMPLETED:
            ActionInstance.objects.create(
                stage_instance=instance.stage_instance,
                action=instance.action,
                action_name_snapshot=instance.action.name,
                status=ActionInstanceStatus.PENDING,
                execution_no=instance.execution_no + 1,
                responsible=instance.responsible,
            )
            return
        instance.status = ActionInstanceStatus.PENDING
        instance.planned_start = None
        instance.planned_end = None
        instance.actual_start = None
        instance.actual_end = None
        instance.triggered_at = None
        instance.save(
            update_fields=[
                "status",
                "planned_start",
                "planned_end",
                "actual_start",
                "actual_end",
                "triggered_at",
            ],
        )

    def _return_to_stage(
        self,
        target: StageInstance,
        mode: str,
        last_action: ActionInstance | None,
        now: datetime,
        trace: _Trace,
    ) -> None:
        """Снова открывает этап возврата: целиком или только последним обязательным действием."""
        if mode == RollbackMode.RESTART:
            for instance in self._latest_action_instances(stage_instance=target).values():
                self._reset_action(instance=instance)
        else:
            self._reset_action(instance=last_action)
        target.status = StageInstanceStatus.IN_PROGRESS
        target.completed_at = None
        target.save(update_fields=["status", "completed_at"])
        self._activate_ready(stage_instance=target, now=now, trace=trace)
        if self._is_closable(stage_instance=target):
            self._close_stage(stage_instance=target, now=now, trace=trace)


workflow_engine_service = WorkflowEngineService()
