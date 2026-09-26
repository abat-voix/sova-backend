from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from sova.catalog.enum import CatalogType
from sova.catalog.models import CatalogImportMapping
from sova.catalog.schemas import CATALOG_IMPORT_FIELDS


class CatalogImportMappingTestCase(TestCase):
    """Маппинг колонка→канонический ключ уникален по каждой стороне в рамках catalog_type."""

    def test_creates_mapping_row(self) -> None:
        mapping = CatalogImportMapping.objects.create(
            catalog_type=CatalogType.VENDOR,
            source_column="Наименование вендора",
            target_field="name",
        )
        self.assertEqual(str(mapping), "vendor: Наименование вендора → name")

    def test_source_column_unique_per_catalog_type(self) -> None:
        CatalogImportMapping.objects.create(
            catalog_type=CatalogType.VENDOR, source_column="Название", target_field="name"
        )
        with transaction.atomic(), self.assertRaises(IntegrityError):
            CatalogImportMapping.objects.create(
                catalog_type=CatalogType.VENDOR, source_column="Название", target_field="external_code"
            )

    def test_target_field_unique_per_catalog_type(self) -> None:
        CatalogImportMapping.objects.create(
            catalog_type=CatalogType.VENDOR, source_column="Название", target_field="name"
        )
        with transaction.atomic(), self.assertRaises(IntegrityError):
            CatalogImportMapping.objects.create(
                catalog_type=CatalogType.VENDOR, source_column="Наименование", target_field="name"
            )

    def test_same_source_column_allowed_across_different_catalog_types(self) -> None:
        CatalogImportMapping.objects.create(
            catalog_type=CatalogType.VENDOR, source_column="Название", target_field="name"
        )
        CatalogImportMapping.objects.create(
            catalog_type=CatalogType.DIRECTION, source_column="Название", target_field="name"
        )

    def test_clean_rejects_unknown_target_field(self) -> None:
        mapping = CatalogImportMapping(catalog_type=CatalogType.VENDOR, source_column="Название", target_field="nmae")

        with self.assertRaises(ValidationError) as context:
            mapping.full_clean()

        self.assertIn("target_field", context.exception.message_dict)

    def test_clean_accepts_optional_target_field(self) -> None:
        mapping = CatalogImportMapping(
            catalog_type=CatalogType.PRODUCT, source_column="Активен", target_field="is_active"
        )

        mapping.full_clean()


class CatalogImportFieldsTestCase(TestCase):
    """Набор канонических полей описан для каждого типа каталога."""

    def test_every_catalog_type_has_fields(self) -> None:
        self.assertEqual(set(CATALOG_IMPORT_FIELDS), set(CatalogType))

    def test_required_fields_are_subset_of_all_fields(self) -> None:
        for catalog_type, fields in CATALOG_IMPORT_FIELDS.items():
            self.assertLessEqual(fields.required, fields.all, msg=catalog_type)
