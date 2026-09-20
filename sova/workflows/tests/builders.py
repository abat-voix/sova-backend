from sova.processes.enum import StageInstanceContextType
from sova.workflows.enum import Audience
from sova.workflows.models import ActionOutcome, ActionTransition, WorkflowAction, WorkflowStage
from sova.workflows.services import action_outcome_service
from sova.workflows.tests.factories import (
    ActionDependencyFactory,
    ActionOutcomeFactory,
    ActionTransitionFactory,
    StageTransitionFactory,
    WorkflowActionFactory,
    WorkflowFactory,
    WorkflowStageFactory,
)


class WorkflowBuilder:
    """
    Собирает граф workflow для тестов движка: этапы, связи между ними, действия, зависимости и исходы.

    Каждое действие сразу получает исход «Выполнено» (код `done`), как при создании через API.
    """

    def __init__(self, audience: str = Audience.B2B) -> None:
        """Создаёт пустой workflow."""
        self.workflow = WorkflowFactory(audience=audience)
        self._stage_order = 0
        self._action_order: dict = {}

    def stage(
        self,
        name: str,
        after: tuple[WorkflowStage, ...] = (),
        type: str = StageInstanceContextType.INTERACTION,
    ) -> WorkflowStage:
        """Добавляет этап и связи «после закрытия этапов `after`»."""
        self._stage_order += 1
        stage = WorkflowStageFactory(
            workflow=self.workflow,
            name=name,
            type=type,
            sort_order=self._stage_order,
        )
        for source in after:
            StageTransitionFactory(from_stage=source, to_stage=stage)
        return stage

    def action(
        self,
        stage: WorkflowStage,
        name: str,
        optional: bool = False,
        after: tuple[WorkflowAction, ...] = (),
        trigger_only: bool = False,
        duration_days: int | None = None,
    ) -> WorkflowAction:
        """Добавляет действие с зависимостями от действий `after` и исходом «Выполнено»."""
        self._action_order[stage.pk] = self._action_order.get(stage.pk, 0) + 1
        action = WorkflowActionFactory(
            stage=stage,
            name=name,
            sort_order=self._action_order[stage.pk],
            is_optional=optional,
            starts_by_transition_only=trigger_only,
            default_duration_days=duration_days,
        )
        action_outcome_service.create_default(action=action)
        for prerequisite in after:
            ActionDependencyFactory(action=action, depends_on_action=prerequisite)
        return action

    def outcome(self, action: WorkflowAction, code: str, **kwargs) -> ActionOutcome:
        """Добавляет исход действия."""
        return ActionOutcomeFactory(action=action, code=code, name=code, **kwargs)

    def branch(self, outcome: ActionOutcome, target: WorkflowAction, **kwargs) -> ActionTransition:
        """Привязывает к исходу переход на действие `target`."""
        return ActionTransitionFactory(outcome=outcome, target_action=target, **kwargs)
