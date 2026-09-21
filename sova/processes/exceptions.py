class EngineError(Exception):
    """Ошибка движка workflow. Несёт машиночитаемый код, по которому слой API выбирает ответ."""

    default_code = "engine_error"

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or self.default_code


class InvalidStateError(EngineError):
    """Текущее состояние процесса не допускает операцию: действие не в работе, этап не открыт и т.п."""

    default_code = "invalid_state"


class RuleViolationError(EngineError):
    """Операция нарушает правила workflow: чужой исход, пустой обязательный комментарий, нет предшественника и т.п."""

    default_code = "rule_violation"
