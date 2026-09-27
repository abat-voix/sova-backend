from django.test import TestCase

from sova.catalog.enum import CatalogType
from sova.catalog.exceptions import CatalogImportMappingError
from sova.catalog.models import CatalogImportMapping
from sova.catalog.services import catalog_import_mapping_service
from sova.catalog.tests.factories import CatalogImportMappingFactory


class CatalogImportMappingServiceTestCase(TestCase):
    """Маппинг типа каталога читается и заменяется целиком."""

    def _saved(self, catalog_type: str = CatalogType.DIRECTION) -> dict[str, str]:
        """Сохранённый маппинг типа {target_field: source_column}."""
        return dict(
            CatalogImportMapping.objects.filter(catalog_type=catalog_type).values_list("target_field", "source_column")
        )

    def test_replace_creates_mapping(self) -> None:
        """Замена сохраняет непустые пары, пустые колонки пропускаются."""
        catalog_import_mapping_service.replace_for_type(
            catalog_type=CatalogType.DIRECTION,
            mappings={"name": "Название", "external_code": "Код", "is_active": ""},
        )

        # Проверяем, что сохранены только заполненные поля
        self.assertEqual(self._saved(), {"name": "Название", "external_code": "Код"})

    def test_replace_swaps_columns_between_fields(self) -> None:
        """Колонки можно поменять местами — уникальность source_column не мешает."""
        CatalogImportMappingFactory(catalog_type=CatalogType.DIRECTION, target_field="name", source_column="А")
        CatalogImportMappingFactory(catalog_type=CatalogType.DIRECTION, target_field="external_code", source_column="Б")

        catalog_import_mapping_service.replace_for_type(
            catalog_type=CatalogType.DIRECTION, mappings={"name": "Б", "external_code": "А"}
        )

        # Проверяем, что колонки поменялись местами
        self.assertEqual(self._saved(), {"name": "Б", "external_code": "А"})

    def test_replace_removes_omitted_fields(self) -> None:
        """Поле, которого нет в новом маппинге, перестаёт быть замапленным."""
        CatalogImportMappingFactory(catalog_type=CatalogType.DIRECTION, target_field="is_active", source_column="Активен")

        catalog_import_mapping_service.replace_for_type(
            catalog_type=CatalogType.DIRECTION, mappings={"name": "Название", "external_code": "Код"}
        )

        # Проверяем, что is_active удалён
        self.assertNotIn("is_active", self._saved())

    def test_replace_does_not_touch_other_types(self) -> None:
        """Маппинг другого типа не меняется."""
        other = CatalogImportMappingFactory(catalog_type=CatalogType.DIRECTION, target_field="name", source_column="Название")

        catalog_import_mapping_service.replace_for_type(
            catalog_type=CatalogType.VENDOR, mappings={"name": "Название", "external_code": "Код"}
        )

        # Проверяем, что маппинг направлений на месте
        self.assertTrue(CatalogImportMapping.objects.filter(pk=other.pk).exists())

    def test_replace_normalizes_source_column(self) -> None:
        """Колонка сохраняется нормализованной: без лишних и неразрывных пробелов."""
        catalog_import_mapping_service.replace_for_type(
            catalog_type=CatalogType.DIRECTION, mappings={"name": "  Название  вендора ", "external_code": "Код"}
        )

        # Проверяем нормализованное значение
        self.assertEqual(self._saved()["name"], "Название вендора")

    def test_replace_rejects_duplicate_columns_ignoring_case(self) -> None:
        """Колонки, совпадающие без учёта регистра и пробелов, — дубль."""
        with self.assertRaises(CatalogImportMappingError) as context:
            catalog_import_mapping_service.replace_for_type(
                catalog_type=CatalogType.DIRECTION, mappings={"name": "Название", "external_code": " НАЗВАНИЕ"}
            )

        # Проверяем, что ошибка на втором поле
        self.assertEqual(set(context.exception.errors), {"external_code"})

    def test_replace_rejects_duplicate_columns_differing_by_line_break(self) -> None:
        """Колонка с переносом строки и та же колонка в одну строку — дубль, как при сопоставлении файла."""
        with self.assertRaises(CatalogImportMappingError) as context:
            catalog_import_mapping_service.replace_for_type(
                catalog_type=CatalogType.DIRECTION, mappings={"name": "Название\nнаправления", "external_code": "Название направления"}
            )

        # Проверяем, что ошибка на втором поле
        self.assertEqual(set(context.exception.errors), {"external_code"})

    def test_replace_rejects_missing_required_fields(self) -> None:
        """Незаполненное обязательное поле — ошибка, старый маппинг не меняется."""
        CatalogImportMappingFactory(catalog_type=CatalogType.DIRECTION, target_field="name", source_column="Название")

        with self.assertRaises(CatalogImportMappingError) as context:
            catalog_import_mapping_service.replace_for_type(
                catalog_type=CatalogType.DIRECTION, mappings={"name": "Другое", "external_code": ""}
            )

        # Проверяем ошибку и сохранность старого маппинга
        self.assertEqual(set(context.exception.errors), {"external_code"})
        self.assertEqual(self._saved(), {"name": "Название"})

    def test_replace_rejects_unknown_fields(self) -> None:
        """Ключ, которого нет у типа, — ошибка."""
        with self.assertRaises(CatalogImportMappingError) as context:
            catalog_import_mapping_service.replace_for_type(
                catalog_type=CatalogType.DIRECTION,
                mappings={"name": "Название", "external_code": "Код", "programs": "Программы"},
            )

        # Проверяем, что ошибка на неизвестном ключе
        self.assertEqual(set(context.exception.errors), {"programs"})

    def test_get_for_type_lists_required_first(self) -> None:
        """Поля типа: сначала обязательные по алфавиту, затем необязательные; незамапленные — None."""
        CatalogImportMappingFactory(catalog_type=CatalogType.DIRECTION, target_field="is_active", source_column="Активен")

        fields = catalog_import_mapping_service.get_for_type(catalog_type=CatalogType.DIRECTION)

        # Проверяем порядок и значения
        self.assertEqual(
            [(field.target_field, field.required, field.source_column) for field in fields],
            [("external_code", True, None), ("name", True, None), ("is_active", False, "Активен")],
        )
