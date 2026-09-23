from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.catalog.enum import CatalogType
from sova.catalog.models import CatalogImportMapping


class CatalogImportMappingSerializer(serializers.ModelSerializer):
    """Маппинг колонки файла импорта — представление для чтения (list/retrieve)."""

    class Meta:
        model = CatalogImportMapping
        fields = (
            "id",
            "catalog_type",
            "source_column",
            "target_field",
            "created_at",
            "updated_at",
        )


class CatalogImportFieldsQuerySerializer(serializers.Serializer):
    """Параметры запроса списка канонических полей."""

    catalog_type = serializers.ChoiceField(
        choices=CatalogType.choices,
        label=_("Тип каталога"),
        help_text=_("Тип, для которого нужен список допустимых target_field"),
    )


class CatalogImportFieldSerializer(serializers.Serializer):
    """Каноническое поле импорта — допустимое значение target_field маппинга."""

    name = serializers.CharField(
        label=_("Поле"),
        help_text=_("Значение для target_field маппинга"),
    )
    required = serializers.BooleanField(
        label=_("Обязательное"),
        help_text=_("Без колонки, замапленной на это поле, файл этого типа не загрузится"),
    )


class CatalogImportTypeMappingFieldSerializer(serializers.Serializer):
    """Каноническое поле типа каталога и колонка файла, замапленная на него."""

    target_field = serializers.CharField(
        label=_("Поле"),
        help_text=_("Канонический ключ, который понимает обработчик импорта"),
    )
    required = serializers.BooleanField(
        label=_("Обязательное"),
        help_text=_("Без колонки, замапленной на это поле, файл этого типа не загрузится"),
    )
    source_column = serializers.CharField(
        allow_null=True,
        label=_("Колонка в файле"),
        help_text=_("Заголовок колонки файла; null — поле не замаплено"),
    )


class WriteCatalogImportTypeMappingSerializer(serializers.Serializer):
    """Полная замена маппинга типа каталога."""

    mappings = serializers.DictField(
        child=serializers.CharField(allow_blank=True, allow_null=True, max_length=255),
        label=_("Маппинг"),
        help_text=_(
            "{канонический ключ: заголовок колонки}. Пустое значение или отсутствующий ключ — поле не замаплено. "
            "Обязательные ключи типа должны быть заполнены, колонки не повторяются (без учёта регистра)"
        ),
    )
