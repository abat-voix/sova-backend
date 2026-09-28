from django.core.validators import FileExtensionValidator
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.catalog.enum import CatalogType

# Типы, которые загружает импорт каталогов; обучающиеся — своим эндпоинтом обучения (/api/training/learners/import/)
CATALOG_IMPORT_CHOICES = [choice for choice in CatalogType.choices if choice[0] != CatalogType.LEARNER]


class CatalogImportSerializer(serializers.Serializer):
    """Загрузка файла каталога или реестра договоров — валидация входных данных."""

    catalog_type = serializers.ChoiceField(
        choices=CATALOG_IMPORT_CHOICES,
        label=_("Тип каталога"),
        help_text=_("Определяет обработчик и маппинг колонок файла"),
    )
    file = serializers.FileField(
        validators=[FileExtensionValidator(allowed_extensions=("xlsx", "xls"))],
        label=_("Файл"),
        help_text=_("Первый лист xlsx или xls; первая строка — заголовки колонок из маппинга типа"),
    )


class CatalogImportHeadersSerializer(serializers.Serializer):
    """Файл, заголовки которого нужно прочитать для настройки маппинга."""

    file = serializers.FileField(
        validators=[FileExtensionValidator(allowed_extensions=("xlsx", "xls"))],
        label=_("Файл"),
        help_text=_("Первый лист xlsx или xls; читается только первая строка"),
    )


class CatalogImportHeadersResultSerializer(serializers.Serializer):
    """Заголовки файла."""

    headers = serializers.ListField(
        child=serializers.CharField(),
        label=_("Заголовки"),
        help_text=_("Непустые заголовки первой строки первого листа в порядке файла, без повторов"),
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


class CatalogImportRowWarningSerializer(serializers.Serializer):
    """Предупреждение по строке файла импорта: строка загружена, но часть данных не применена."""

    row = serializers.IntegerField(
        label=_("Строка"),
        help_text=_("Номер строки в файле, как в Excel: первая строка — заголовки"),
    )
    message = serializers.CharField(
        label=_("Сообщение"),
        help_text=_("Что именно не применено и почему"),
    )


class CatalogImportResultSerializer(serializers.Serializer):
    """Результат успешного импорта."""

    catalog_type = serializers.ChoiceField(
        choices=CATALOG_IMPORT_CHOICES,
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
    warnings = CatalogImportRowWarningSerializer(
        many=True,
        label=_("Предупреждения"),
        help_text=_(
            "Строки загружены, но часть данных не применена (например, менеджер реестра не найден среди "
            "пользователей и не назначен ответственным); пустой список — предупреждений нет"
        ),
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
