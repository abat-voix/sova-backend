from dataclasses import dataclass

from sova.processes.enum import StageInstanceContextType
from sova.workflows.enum import Audience


@dataclass(frozen=True)
class OutcomeSpec:
    """
    Исход действия в декларации шаблона.

    `starts` — имя действия того же этапа, которое запускает этот исход (переход по исходу).
    """

    code: str
    name: str
    is_comment_required: bool = False
    is_attachment_required: bool = False
    starts: str | None = None


@dataclass(frozen=True)
class ActionSpec:
    """
    Действие этапа в декларации шаблона.

    `after` — имена действий того же этапа, которые должны быть выполнены раньше. Без объявленных
    исходов действие получает «Выполнено» — иначе его нельзя завершить.
    """

    name: str
    description: str = ""
    duration_days: int | None = None
    is_optional: bool = False
    is_trigger_only: bool = False
    after: tuple[str, ...] = ()
    outcomes: tuple[OutcomeSpec, ...] = ()


@dataclass(frozen=True)
class StageSpec:
    """Этап в декларации шаблона. `after` — имена этапов, после закрытия которых он открывается."""

    name: str
    type: str = StageInstanceContextType.INTERACTION
    description: str = ""
    after: tuple[str, ...] = ()
    is_optional: bool = False
    actions: tuple[ActionSpec, ...] = ()


@dataclass(frozen=True)
class WorkflowSpec:
    """
    Декларация шаблона workflow: сам процесс и его этапы по порядку.

    Первый этап помечается начальным, последний — финальным. Связи между этапами задаются
    именами в `StageSpec.after`, а не порядком объявления: `sort_order` определяет только
    отображение.
    """

    code: str
    name: str
    audience: str = Audience.B2B
    description: str = ""
    stale_threshold_days: int | None = None
    stages: tuple[StageSpec, ...] = ()
