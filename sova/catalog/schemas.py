from dataclasses import dataclass

from sova.catalog.enum import CatalogType


@dataclass(frozen=True)
class ImportRowError:
    """Ошибка одной строки файла импорта каталога."""

    row_number: int
    message: str

    def __str__(self) -> str:
        return f"Строка {self.row_number}: {self.message}"


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
    CatalogType.VENDOR: CatalogImportFields(
        required=frozenset({"name", "external_code"}),
        optional=frozenset({"is_active"}),
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
        optional=frozenset({"position", "email", "phone"}),
    ),
    CatalogType.CONTRACT_REGISTRY: CatalogImportFields(
        required=frozenset({"university", "vendor", "product", "contract_number"}),
        optional=frozenset({
            "direction", "program", "license_signed", "license_valid_until_year", "university_contact",
            "draft_manager_full_name", "draft_status", "draft_comment",
        }),
    ),
}
