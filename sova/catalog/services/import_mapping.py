from dataclasses import dataclass

from django.db import transaction

from sova.catalog.exceptions import CatalogImportMappingError
from sova.catalog.models import CatalogImportMapping
from sova.catalog.schemas import CATALOG_IMPORT_FIELD_LABELS, CATALOG_IMPORT_FIELDS
from sova.core.text import header_key, normalize_text


@dataclass(frozen=True)
class MappingField:
    """Каноническое поле типа каталога и колонка файла, замапленная на него (None — не замаплено)."""

    target_field: str
    required: bool
    source_column: str | None

    @property
    def label(self) -> str:
        """Подпись поля для интерфейса."""
        return CATALOG_IMPORT_FIELD_LABELS[self.target_field]


class CatalogImportMappingService:
    """
    Маппинг импорта целиком для одного catalog_type: чтение всех канонических полей и атомарная замена.

    Маппинг меняется только целиком: так смена колонок местами не упирается в уникальность
    source_column, а незаполненные обязательные поля и дубли колонок отсекаются до записи в БД.
    Дубли сравниваются так же, как импорт сопоставляет заголовки файла (`header_key`).
    """

    def get_for_type(self, catalog_type: str) -> list[MappingField]:
        """Все канонические поля типа (сначала обязательные) с текущими колонками файла."""
        configured = dict(
            CatalogImportMapping.objects.filter(catalog_type=catalog_type).values_list(
                "target_field", "source_column"
            )
        )
        fields = CATALOG_IMPORT_FIELDS[catalog_type]
        return [
            MappingField(target_field=name, required=True, source_column=configured.get(name))
            for name in sorted(fields.required)
        ] + [
            MappingField(target_field=name, required=False, source_column=configured.get(name))
            for name in sorted(fields.optional)
        ]

    @transaction.atomic
    def replace_for_type(self, catalog_type: str, mappings: dict[str, str | None]) -> list[MappingField]:
        """
        Заменяет маппинг типа на `mappings` ({канонический ключ: колонка файла}).

        Пустая колонка или отсутствующий ключ — поле не замаплено. При ошибке ничего не меняется.
        """
        cleaned = self._validate(catalog_type=catalog_type, mappings=mappings)

        CatalogImportMapping.objects.filter(catalog_type=catalog_type).delete()
        CatalogImportMapping.objects.bulk_create(
            CatalogImportMapping(catalog_type=catalog_type, source_column=source_column, target_field=target_field)
            for target_field, source_column in cleaned.items()
        )
        return self.get_for_type(catalog_type=catalog_type)

    def _validate(self, catalog_type: str, mappings: dict[str, str | None]) -> dict[str, str]:
        """Нормализует колонки и проверяет ключи, обязательные поля и дубли; возвращает непустые пары."""
        fields = CATALOG_IMPORT_FIELDS[catalog_type]
        errors: dict[str, str] = {}
        cleaned: dict[str, str] = {}
        used_by: dict[str, str] = {}

        for target_field, source_column in mappings.items():
            if target_field not in fields.all:
                errors[target_field] = "Недопустимое поле для этого типа каталога."
                continue
            source_column = normalize_text(source_column or "")
            if not source_column:
                continue

            key = header_key(source_column)
            if key in used_by:
                errors[target_field] = f"Колонка уже используется для поля {used_by[key]}."
                continue
            used_by[key] = target_field
            cleaned[target_field] = source_column

        for target_field in sorted(fields.required - cleaned.keys()):
            errors.setdefault(target_field, "Обязательное поле: укажите колонку файла.")

        if errors:
            raise CatalogImportMappingError(errors=errors)
        return cleaned


catalog_import_mapping_service = CatalogImportMappingService()
