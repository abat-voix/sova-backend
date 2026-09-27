from dataclasses import dataclass
from typing import NamedTuple

from sova.catalog.enum import CatalogType


@dataclass(frozen=True)
class ImportRowError:
    """Ошибка одной строки файла импорта каталога."""

    row_number: int
    message: str

    def __str__(self) -> str:
        return f"Строка {self.row_number}: {self.message}"


@dataclass(frozen=True)
class ImportRowWarning:
    """Предупреждение по строке файла импорта: строка загружена, но часть данных не применена."""

    row_number: int
    message: str

    def __str__(self) -> str:
        return f"Строка {self.row_number}: {self.message}"


class CatalogImportResult(NamedTuple):
    """Итог импорта файла: создано, обновлено и предупреждения по строкам."""

    created: int
    updated: int
    warnings: list[ImportRowWarning]


@dataclass(frozen=True)
class CatalogImportFields:
    """Канонические поля импорта одного типа каталога — допустимые значения `target_field` маппинга."""

    required: frozenset[str]
    optional: frozenset[str] = frozenset()

    @property
    def all(self) -> frozenset[str]:
        """Все допустимые поля: обязательные и необязательные."""
        return self.required | self.optional


# Ключи, которые понимают обработчики импорта в sova/catalog/services/ (по значению CatalogType).
CATALOG_IMPORT_FIELDS = {
    CatalogType.UNIVERSITY: CatalogImportFields(
        required=frozenset({
            "id", "ror", "name_en", "name", "short_name", "country_code", "type",
            "works_count", "cited_by_count", "city", "region", "lat", "lon", "homepage_url",
        }),
    ),
    # Справочник вендоров (name/external_code) или файл «вендор + продукты + контактное лицо» (Вендоры.xlsx).
    CatalogType.VENDOR: CatalogImportFields(
        required=frozenset({"name"}),
        optional=frozenset({
            "external_code", "is_active", "products",
            "contact_full_name", "contact_email", "contact_phone", "contact_telegram", "contact_position",
            "contact_channels",
        }),
    ),
    CatalogType.DIRECTION: CatalogImportFields(
        required=frozenset({"name", "external_code"}),
        optional=frozenset({"is_active"}),
    ),
    CatalogType.PROGRAM: CatalogImportFields(
        required=frozenset({"name", "direction"}),
        optional=frozenset({"is_active"}),
    ),
    CatalogType.PRODUCT: CatalogImportFields(
        required=frozenset({"name", "external_code", "vendor"}),
        optional=frozenset({"is_active", "programs"}),
    ),
    CatalogType.CONTACT_PERSON: CatalogImportFields(
        required=frozenset({"full_name", "university"}),
        optional=frozenset({"position", "email", "phone", "telegram", "channels"}),
    ),
    CatalogType.CONTRACT_REGISTRY: CatalogImportFields(
        required=frozenset({"university", "vendor", "product", "contract_number"}),
        optional=frozenset({
            "direction", "program", "license_signed", "license_valid_until_year", "university_contact",
            "manager_full_name", "draft_status", "draft_comment",
        }),
    ),
}
