from django.core.exceptions import ValidationError
from django.db import models

from sova.catalog.enum import CatalogType
from sova.catalog.schemas import CATALOG_IMPORT_FIELDS
from sova.core.models import TimeStampedModel


class CatalogImportMapping(TimeStampedModel):
    """
    Соответствие «колонка файла → канонический ключ» для одного catalog_type.

    `target_field` — не путь ORM-поля, а ключ, который знает обработчик импорта в
    `sova/catalog/services/`; допустимые ключи типа — `CATALOG_IMPORT_FIELDS` (sova/catalog/schemas.py).
    """

    catalog_type = models.CharField(
        max_length=32,
        choices=CatalogType.choices,
        verbose_name="Тип каталога",
    )
    source_column = models.CharField(
        max_length=255,
        verbose_name="Колонка в файле",
    )
    target_field = models.CharField(
        max_length=64,
        verbose_name="Каноническое поле",
    )

    class Meta:
        verbose_name = "Маппинг импорта каталога"
        verbose_name_plural = "Маппинги импорта каталогов"
        ordering = ["catalog_type", "target_field"]
        constraints = [
            models.UniqueConstraint(
                fields=["catalog_type", "source_column"],
                name="unique_mapping_source_column",
            ),
            models.UniqueConstraint(
                fields=["catalog_type", "target_field"],
                name="unique_mapping_target_field",
            ),
        ]

    def clean(self):
        # Неизвестный catalog_type отсекает валидация choices, здесь — только target_field.
        fields = CATALOG_IMPORT_FIELDS.get(self.catalog_type)
        if fields is not None and self.target_field not in fields.all:
            allowed = ", ".join(sorted(fields.all))
            raise ValidationError({"target_field": f"Недопустимое поле для этого типа. Допустимые: {allowed}."})

    def __str__(self):
        return f"{self.catalog_type}: {self.source_column} → {self.target_field}"
