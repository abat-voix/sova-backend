from django.core.exceptions import ValidationError as DjangoValidationError
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


class WriteCatalogImportMappingSerializer(serializers.ModelSerializer):
    """Маппинг колонки файла импорта — валидация входных данных (create/update)."""

    class Meta:
        model = CatalogImportMapping
        fields = (
            "id",
            "catalog_type",
            "source_column",
            "target_field",
        )

    def validate(self, attrs: dict) -> dict:
        """target_field должен быть полем выбранного типа — в том числе при PATCH одного из двух полей."""
        mapping = CatalogImportMapping(
            catalog_type=attrs.get("catalog_type", getattr(self.instance, "catalog_type", None)),
            target_field=attrs.get("target_field", getattr(self.instance, "target_field", None)),
        )
        try:
            mapping.clean()
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.message_dict) from error
        return attrs


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
