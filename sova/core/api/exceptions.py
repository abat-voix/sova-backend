from django.db import IntegrityError
from django.db.models import ProtectedError
from django.utils.translation import gettext_lazy as _
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


class ConflictError(APIException):
    """Конфликт с текущим состоянием данных (HTTP 409)."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = _("Операция конфликтует с текущим состоянием данных.")
    default_code = "conflict"


def exception_handler(exc: Exception, context: dict) -> Response | None:
    """
    Обработчик ошибок API.

    Ошибки БД, которые иначе превратились бы в 500, отдаются как 409 с кодом:
    `protected` — удаляемый объект защищён связями (on_delete=PROTECT),
    `integrity_error` — нарушено ограничение целостности, не пойманное валидацией.
    Ко всем ответам вида `{"detail": ...}` добавляется машиночитаемое поле `code`.
    """
    if isinstance(exc, ProtectedError):
        exc = ConflictError(
            detail=_("Объект нельзя удалить: на него ссылаются другие объекты."),
            code="protected",
        )
    elif isinstance(exc, IntegrityError):
        exc = ConflictError(
            detail=_("Нарушено ограничение целостности данных."),
            code="integrity_error",
        )

    response = drf_exception_handler(exc, context)
    if (
        response is not None
        and isinstance(response.data, dict)
        and "detail" in response.data
        and "code" not in response.data
    ):
        response.data["code"] = getattr(response.data["detail"], "code", None)
    return response
