from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from sova.catalog.enum import CatalogType
from sova.catalog.models import CatalogImportMapping
from sova.catalog.tests.factories import CatalogImportMappingFactory
from sova.core.tests.base import BaseApiTestMixin
from sova.core.tests.factories import UserFactory


class CatalogImportMappingApiTestCase(BaseApiTestMixin, APITestCase):
    """Тесты CRUD /api/catalog/import-mappings/."""

    url_basename = "catalog:import-mapping"
    model = CatalogImportMapping

    def create_instance(self, **kwargs) -> CatalogImportMapping:
        """Создаёт маппинг колонки."""
        return CatalogImportMappingFactory(**kwargs)

    def get_expected_data(self, instance: CatalogImportMapping) -> dict:
        """Поля read-представления маппинга."""
        return {
            "id": str(instance.pk),
            "catalog_type": instance.catalog_type,
            "source_column": instance.source_column,
            "target_field": instance.target_field,
        }

    def get_post_data(self) -> dict:
        """Данные создания маппинга."""
        return {"catalog_type": CatalogType.VENDOR, "source_column": "Наименование вендора", "target_field": "name"}

    def get_change_data(self) -> dict:
        """Данные обновления маппинга."""
        return {"source_column": "Название"}

    def get_search_term(self, instance: CatalogImportMapping) -> str:
        """Поиск по колонке файла."""
        return instance.source_column

    def test_filter_by_catalog_type_returns_only_matching(self) -> None:
        """Фильтр catalog_type возвращает только маппинги этого типа."""
        CatalogImportMappingFactory(catalog_type=CatalogType.PRODUCT, target_field="name")
        vendor_mapping = CatalogImportMappingFactory(catalog_type=CatalogType.VENDOR, target_field="name")

        response = self.client.get(path=self.list_url, data={"catalog_type": CatalogType.VENDOR})

        # Проверяем, что найден только маппинг вендоров
        self.assertEqual(
            [item["id"] for item in response.data["results"]],
            [str(vendor_mapping.pk)],
        )

    def test_create_returns_400_with_unknown_target_field(self) -> None:
        """Поле, которого нет у типа каталога, отклоняется."""
        data = {"catalog_type": CatalogType.VENDOR, "source_column": "Вендор", "target_field": "programs"}

        response = self.client.post(path=self.list_url, data=data, format="json")

        # Проверяем, что ошибка указывает на target_field
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("target_field", response.data)

    def test_change_returns_400_when_type_changes_to_incompatible(self) -> None:
        """Смена типа проверяет уже сохранённое поле против нового типа."""
        mapping = CatalogImportMappingFactory(catalog_type=CatalogType.PRODUCT, target_field="programs")

        response = self.client.patch(
            path=self.detail_url(mapping),
            data={"catalog_type": CatalogType.VENDOR},
            format="json",
        )

        # Проверяем, что у вендора нет поля programs
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("target_field", response.data)

    def test_create_returns_400_with_duplicate_target_field(self) -> None:
        """Одно каноническое поле нельзя замапить на две колонки одного типа."""
        CatalogImportMappingFactory(catalog_type=CatalogType.VENDOR, target_field="name")
        data = {"catalog_type": CatalogType.VENDOR, "source_column": "Другая колонка", "target_field": "name"}

        response = self.client.post(path=self.list_url, data=data, format="json")

        # Проверяем, что дубль отклонён валидацией, а не ошибкой БД
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class CatalogImportFieldsApiTestCase(APITestCase):
    """Тесты GET /api/catalog/import-mappings/fields/."""

    def setUp(self) -> None:
        """Аутентифицирует клиента."""
        self.client.force_authenticate(user=UserFactory())
        self.url = reverse("catalog:import-mapping-fields")

    def test_returns_fields_of_catalog_type_with_required_flag(self) -> None:
        """Возвращает допустимые поля типа с пометкой обязательности."""
        response = self.client.get(path=self.url, data={"catalog_type": CatalogType.PRODUCT})

        # Проверяем состав и обязательность полей продукта
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data,
            [
                {"name": "external_code", "required": True},
                {"name": "name", "required": True},
                {"name": "vendor", "required": True},
                {"name": "is_active", "required": False},
                {"name": "programs", "required": False},
            ],
        )

    def test_returns_400_without_catalog_type(self) -> None:
        """Без catalog_type возвращается 400."""
        response = self.client.get(path=self.url)

        # Проверяем, что ошибка указывает на catalog_type
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("catalog_type", response.data)
