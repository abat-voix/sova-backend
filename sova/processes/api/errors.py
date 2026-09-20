from contextlib import contextmanager
from collections.abc import Iterator

from rest_framework import status
from rest_framework.exceptions import APIException

from sova.core.api.exceptions import ConflictError
from sova.processes.exceptions import InvalidStateError, RuleViolationError


class RuleViolation(APIException):
    """Операция нарушает правила workflow (HTTP 400). Машиночитаемый код берётся из ошибки движка."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Операция нарушает правила workflow."
    default_code = "rule_violation"


@contextmanager
def translate_engine_errors() -> Iterator[None]:
    """
    Превращает ошибки движка в ответы API: состояние, не допускающее операцию, — 409, нарушение правил — 400.

    Оба ответа несут поле `code` — по нему интерфейс отличает причины отказа.
    """
    try:
        yield
    except InvalidStateError as error:
        raise ConflictError(detail=error.message, code=error.code) from error
    except RuleViolationError as error:
        raise RuleViolation(detail=error.message, code=error.code) from error
