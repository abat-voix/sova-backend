"""Валидаторы полей моделей: подключаются через `validators=` и проверяются в ModelSerializer и формах админки."""

import re

from django.core.exceptions import ValidationError

_INN_RE = re.compile(r"\d{10}|\d{12}")
_PHONE_RE = re.compile(r"\+?[\d\s()\-]+")
PHONE_MIN_DIGITS = 10
PHONE_MAX_DIGITS = 15


def validate_inn(value: str) -> None:
    """ИНН — 10 цифр (юрлицо) или 12 цифр (физлицо, ИП); контрольная сумма не проверяется."""
    if value and not _INN_RE.fullmatch(value):
        raise ValidationError("ИНН должен состоять из 10 или 12 цифр.", code="invalid_inn")


def validate_phone(value: str) -> None:
    """Телефон — цифры с необязательным «+» в начале, пробелами, скобками и дефисами; цифр от 10 до 15."""
    if not value:
        return
    digits = re.sub(r"\D", "", value)
    if not _PHONE_RE.fullmatch(value) or not PHONE_MIN_DIGITS <= len(digits) <= PHONE_MAX_DIGITS:
        raise ValidationError(
            "Телефон может содержать только цифры, «+» в начале, пробелы, скобки и дефисы; "
            f"цифр — от {PHONE_MIN_DIGITS} до {PHONE_MAX_DIGITS}.",
            code="invalid_phone",
        )
