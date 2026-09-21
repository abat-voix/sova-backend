from django.db import IntegrityError
from django.db.models import ProtectedError
from django.test import SimpleTestCase
from rest_framework import status
from rest_framework.exceptions import NotFound

from sova.core.api.exceptions import exception_handler


class ExceptionHandlerTest(SimpleTestCase):
    """Тесты обработчика ошибок API."""

    def test_protected_error_returns_409_with_code(self) -> None:
        """ProtectedError превращается в 409 с кодом protected."""
        exc = ProtectedError("protected", protected_objects=set())

        response = exception_handler(exc=exc, context={})

        # Проверяем статус и машиночитаемый код
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "protected")

    def test_integrity_error_returns_409_with_code(self) -> None:
        """IntegrityError превращается в 409 с кодом integrity_error."""
        response = exception_handler(exc=IntegrityError(), context={})

        # Проверяем статус и машиночитаемый код
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "integrity_error")

    def test_api_exception_gets_code(self) -> None:
        """К ответам DRF добавляется поле code."""
        response = exception_handler(exc=NotFound(), context={})

        # Проверяем, что статус сохранён, а код добавлен
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["code"], "not_found")
