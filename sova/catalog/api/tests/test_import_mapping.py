from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from sova.catalog.enum import CatalogType
from sova.catalog.models import CatalogImportMapping
from sova.catalog.tests.factories import CatalogImportMappingFactory
from sova.core.tests.base import BaseApiTestMixin
from sova.core.tests.factories import UserFactory


class CatalogImportMappingApiTestCase(BaseApiTestMixin, APITestCase):
    """Тесты /api/catalog/import-mappings/ — по записям только чтение, запись через by-type."""

    url_basename = "catalog:import-mapping"
    model = CatalogImportMapping
    allow_create = False
    allow_update = False
    allow_delete = False

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


class CatalogImportTypeMappingApiTestCase(APITestCase):
    """Тесты GET/PUT /api/catalog/import-mappings/by-type/{catalog_type}/."""

    def setUp(self) -> None:
        """Аутентифицирует клиента."""
        self.client.force_authenticate(user=UserFactory())
        self.url = reverse("catalog:import-mapping-by-type", args=[CatalogType.PRODUCT])

    def test_get_returns_all_fields_with_current_columns(self) -> None:
        """GET возвращает все поля типа: сначала обязательные, незамапленные — с null."""
        CatalogImportMappingFactory(catalog_type=CatalogType.PRODUCT, target_field="name", source_column="Название")
        CatalogImportMappingFactory(catalog_type=CatalogType.PRODUCT, target_field="programs", source_column="Программы")

        response = self.client.get(path=self.url)

        # Проверяем состав полей, обязательность и колонки
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data,
            [
                {"target_field": "external_code", "required": True, "source_column": None},
                {"target_field": "name", "required": True, "source_column": "Название"},
                {"target_field": "vendor", "required": True, "source_column": None},
                {"target_field": "is_active", "required": False, "source_column": None},
                {"target_field": "programs", "required": False, "source_column": "Программы"},
            ],
        )

    def test_get_returns_404_for_unknown_catalog_type(self) -> None:
        """Неизвестный тип каталога — 404."""
        response = self.client.get(path=reverse("catalog:import-mapping-by-type", args=["unknown"]))

        # Проверяем, что тип не найден
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_requires_authentication(self) -> None:
        """Анонимный запрос отклоняется."""
        self.client.force_authenticate(user=None)

        response = self.client.get(path=self.url)

        # Проверяем, что доступ запрещён
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_put_replaces_mapping_of_type(self) -> None:
        """PUT заменяет маппинг типа целиком и возвращает новое состояние."""
        CatalogImportMappingFactory(catalog_type=CatalogType.PRODUCT, target_field="programs", source_column="Старое")
        data = {"mappings": {"name": "Название", "external_code": "Артикул", "vendor": "Вендор", "programs": ""}}

        response = self.client.put(path=self.url, data=data, format="json")

        # Проверяем ответ и сохранённый маппинг: programs очищен
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
        self.assertEqual(
            {item["target_field"]: item["source_column"] for item in response.data},
            {"external_code": "Артикул", "name": "Название", "vendor": "Вендор", "is_active": None, "programs": None},
        )
        self.assertEqual(
            dict(
                CatalogImportMapping.objects.filter(catalog_type=CatalogType.PRODUCT).values_list(
                    "target_field", "source_column"
                )
            ),
            {"name": "Название", "external_code": "Артикул", "vendor": "Вендор"},
        )

    def test_put_returns_400_with_errors_by_field(self) -> None:
        """Ошибки возвращаются по ключам и ничего не сохраняется."""
        data = {"mappings": {"name": "Название", "external_code": "название ", "programs_x": "X"}}

        response = self.client.put(path=self.url, data=data, format="json")

        # Проверяем ошибки: дубль колонки, неизвестный ключ, пустое обязательное поле
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(set(response.data["mappings"]), {"external_code", "programs_x", "vendor"})
        self.assertFalse(CatalogImportMapping.objects.exists())

    def test_put_returns_400_without_mappings(self) -> None:
        """Без mappings — 400."""
        response = self.client.put(path=self.url, data={}, format="json")

        # Проверяем, что ошибка указывает на mappings
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("mappings", response.data)
