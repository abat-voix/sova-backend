from django.core.validators import FileExtensionValidator
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.catalog.enum import CatalogType


class CatalogImportSerializer(serializers.Serializer):
    """Загрузка файла каталога или реестра договоров — валидация входных данных."""

    catalog_type = serializers.ChoiceField(
        choices=CatalogType.choices,
        label=_("Тип каталога"),
        help_text=_("Определяет обработчик и маппинг колонок файла"),
    )
    file = serializers.FileField(
        validators=[FileExtensionValidator(allowed_extensions=("xlsx", "xls"))],
        label=_("Файл"),
        help_text=_("Первый лист xlsx или xls; первая строка — заголовки колонок из маппинга типа"),
    )


class CatalogImportResultSerializer(serializers.Serializer):
    """Результат успешного импорта."""

    catalog_type = serializers.ChoiceField(
        choices=CatalogType.choices,
        label=_("Тип каталога"),
        help_text=_("Тип, переданный в запросе"),
    )
    created = serializers.IntegerField(
        label=_("Создано"),
        help_text=_("Для реестра договоров — число договоров, а не строк файла"),
    )
    updated = serializers.IntegerField(
        label=_("Обновлено"),
        help_text=_("Записи, найденные по коду или названию и перезаписанные данными файла"),
    )


class CatalogImportRowErrorSerializer(serializers.Serializer):
    """Ошибка одной строки файла импорта."""

    row = serializers.IntegerField(
        label=_("Строка"),
        help_text=_("Номер строки в файле, как в Excel: первая строка — заголовки"),
    )
    message = serializers.CharField(
        label=_("Сообщение"),
        help_text=_("Причина, по которой строку не удалось загрузить"),
    )


class CatalogImportErrorSerializer(serializers.Serializer):
    """Ошибка импорта: файл целиком (import_error) или строки файла (import_failed)."""

    detail = serializers.CharField(
        label=_("Описание"),
        help_text=_("Текст ошибки для показа пользователю"),
    )
    code = serializers.CharField(
        label=_("Код"),
        help_text=_("import_error — ошибка файла целиком, import_failed — ошибки в строках"),
    )
    errors = CatalogImportRowErrorSerializer(
        many=True,
        required=False,
        label=_("Ошибки строк"),
        help_text=_("Только для import_failed; не больше 100, полное число — в errors_total"),
    )
    errors_total = serializers.IntegerField(
        required=False,
        label=_("Всего ошибок"),
        help_text=_("Только для import_failed; импорт при этом откатывается целиком"),
    )
