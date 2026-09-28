"""
Зашифрованные поля модели (`sova.core.crypto`).

В БД хранится текст шифра, в Python — обычное значение: строка, дата или JSON. Фильтровать и сортировать по таким
полям в БД нельзя — шифр каждый раз разный; доступен только `isnull`, для поиска используется отдельное поле с
`blind_index`.
"""

import datetime
import json

from django.core.exceptions import FieldError
from django.db import models

from sova.core.crypto import decrypt, encrypt


class EncryptedTextField(models.TextField):
    """Строка, которая хранится зашифрованной."""

    def from_db_value(self, value, expression, connection):
        if value is None:
            return None
        return self.from_plaintext(decrypt(value))

    def get_prep_value(self, value):
        value = self.to_python(value)
        if value is None:
            return None
        return encrypt(self.to_plaintext(value))

    def get_lookup(self, lookup_name):
        if lookup_name != "isnull":
            raise FieldError(f"Поиск по зашифрованному полю «{self.name}» недоступен: {lookup_name}.")
        return super().get_lookup(lookup_name)

    def to_python(self, value):
        if value is None or isinstance(value, str):
            return value
        return str(value)

    def to_plaintext(self, value) -> str:
        """Значение Python → открытый текст перед шифрованием."""
        return value

    def from_plaintext(self, value: str):
        """Открытый текст после расшифровки → значение Python."""
        return value


class EncryptedDateField(EncryptedTextField):
    """Дата, которая хранится зашифрованной (ISO-строка под шифром)."""

    def to_python(self, value):
        if value in (None, ""):
            return None
        if isinstance(value, datetime.datetime):
            return value.date()
        if isinstance(value, datetime.date):
            return value
        return datetime.date.fromisoformat(str(value))

    def to_plaintext(self, value) -> str:
        return value.isoformat()

    def from_plaintext(self, value: str):
        return datetime.date.fromisoformat(value) if value else None

    def formfield(self, **kwargs):
        return models.DateField(null=self.null, blank=self.blank).formfield(**kwargs)


class EncryptedJSONField(EncryptedTextField):
    """JSON, который хранится зашифрованным."""

    def to_python(self, value):
        return value

    def to_plaintext(self, value) -> str:
        return json.dumps(value, ensure_ascii=False, default=str)

    def from_plaintext(self, value: str):
        return json.loads(value) if value else None
