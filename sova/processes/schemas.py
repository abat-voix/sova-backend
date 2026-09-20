from dataclasses import dataclass, field

from sova.processes.models import ActionInstance, ActionResult, StageInstance, StageRollback


@dataclass
class EngineOutcome:
    """Итог завершения действия: что изменилось в процессе, чтобы интерфейс обновил доску за один запрос."""

    action_instance: ActionInstance
    result: ActionResult
    activated_actions: list[ActionInstance] = field(default_factory=list)
    opened_stages: list[StageInstance] = field(default_factory=list)
    completed_stages: list[StageInstance] = field(default_factory=list)
    workflow_completed: bool = False


@dataclass
class RollbackOutcome:
    """Итог отката: запись журнала, этап, на который вернулся процесс, и сброшенные этапы."""

    rollback: StageRollback
    returned_stage: StageInstance
    reset_stages: list[StageInstance] = field(default_factory=list)
