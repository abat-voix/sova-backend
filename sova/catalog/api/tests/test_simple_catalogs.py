from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from sova.catalog.enum import ClientKind
from sova.catalog.models import B2CClient, Direction, University, Vendor
from sova.catalog.tests.factories import (
    B2CClientFactory,
    DirectionFactory,
    ProductFactory,
    ProgramFactory,
    UniversityFactory,
    VendorFactory,
)
from sova.core.tests.base import BaseApiTestMixin


class VendorApiTestCase(BaseApiTestMixin, APITestCase):
    """Тесты CRUD /api/catalog/vendors/."""

    url_basename = "catalog:vendor"
    model = Vendor

    def create_instance(self, **kwargs) -> Vendor:
        """Создаёт вендора."""
        return VendorFactory(**kwargs)

    def get_expected_data(self, instance: Vendor) -> dict:
        """Поля read-представления вендора."""
        return {
            "id": str(instance.pk),
            "name": instance.name,
            "external_code": instance.external_code,
            "is_active": instance.is_active,
        }

    def get_post_data(self) -> dict:
        """Данные создания вендора."""
        return {"name": "JetBrains", "external_code": "jb"}

    def get_change_data(self) -> dict:
        """Данные обновления вендора."""
        return {"name": "1С", "is_active": False}

    def get_search_term(self, instance: Vendor) -> str:
        """Поиск по названию."""
        return instance.name

    def test_filter_by_is_active_returns_only_matching(self) -> None:
        """Фильтр is_active=false возвращает только неактивных вендоров."""
        VendorFactory(is_active=True)
        inactive = VendorFactory(is_active=False)

        response = self.client.get(path=self.list_url, data={"is_active": "false"})

        # Проверяем, что найден только неактивный вендор
        self.assertEqual(
            [item["id"] for item in response.data["results"]],
            [str(inactive.pk)],
        )

    def test_filter_by_external_code_iexact_ignores_case(self) -> None:
        """Фильтр external_code__iexact находит запись без учёта регистра."""
        target = VendorFactory(external_code="ABC-1")
        VendorFactory(external_code="ABC-2")

        response = self.client.get(
            path=self.list_url,
            data={"external_code__iexact": "abc-1"},
        )

        # Проверяем, что найден только вендор с этим кодом
        self.assertEqual(
            [item["id"] for item in response.data["results"]],
            [str(target.pk)],
        )

    def test_create_returns_400_with_duplicate_name(self) -> None:
        """Создание вендора с занятым названием возвращает 400."""
        VendorFactory(name="Дубль")

        response = self.client.post(
            path=self.list_url,
            data={"name": "Дубль"},
            format="json",
        )

        # Проверяем, что уникальность названия проверена валидацией
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("name", response.data)

    def test_delete_keeps_products_without_vendor(self) -> None:
        """Удаление вендора не удаляет его продукты (SET_NULL)."""
        vendor = VendorFactory()
        product = ProductFactory(vendor=vendor)

        response = self.client.delete(path=self.detail_url(vendor))
        product.refresh_from_db()

        # Проверяем, что вендор удалён
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        # Проверяем, что продукт остался без вендора
        self.assertIsNone(product.vendor)


class DirectionApiTestCase(BaseApiTestMixin, APITestCase):
    """Тесты CRUD /api/catalog/directions/."""

    url_basename = "catalog:direction"
    model = Direction

    def create_instance(self, **kwargs) -> Direction:
        """Создаёт направление."""
        return DirectionFactory(**kwargs)

    def get_expected_data(self, instance: Direction) -> dict:
        """Поля read-представления направления."""
        return {
            "id": str(instance.pk),
            "name": instance.name,
            "external_code": instance.external_code,
            "is_active": instance.is_active,
        }

    def get_post_data(self) -> dict:
        """Данные создания направления."""
        return {"name": "DevOps"}

    def get_change_data(self) -> dict:
        """Данные обновления направления."""
        return {"name": "QA", "is_active": False}

    def get_search_term(self, instance: Direction) -> str:
        """Поиск по названию."""
        return instance.name

    def test_delete_returns_409_when_direction_has_programs(self) -> None:
        """Удаление направления с программами возвращает 409 с кодом protected."""
        direction = DirectionFactory()
        ProgramFactory(direction=direction)

        response = self.client.delete(path=self.detail_url(direction))

        # Проверяем, что защита PROTECT превращается в 409, а не 500
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "protected")


class UniversityApiTestCase(BaseApiTestMixin, APITestCase):
    """Тесты CRUD /api/catalog/universities/."""

    url_basename = "catalog:university"
    model = University

    def create_instance(self, **kwargs) -> University:
        """Создаёт вуз."""
        return UniversityFactory(**kwargs)

    def get_expected_data(self, instance: University) -> dict:
        """Поля read-представления вуза."""
        return {
            "id": str(instance.pk),
            "name": instance.name,
            "inn": instance.inn,
            "external_code": instance.external_code,
            "email": instance.email,
            "phone": instance.phone,
            "is_active": instance.is_active,
        }

    def get_post_data(self) -> dict:
        """Данные создания вуза."""
        return {"name": "МГУ", "inn": "7729082090", "email": "info@msu.ru"}

    def get_change_data(self) -> dict:
        """Данные обновления вуза."""
        return {"name": "СПбГУ", "phone": "+7 812 000-00-00"}

    def get_search_term(self, instance: University) -> str:
        """Поиск по названию."""
        return instance.name

    def test_filter_by_inn_iexact_returns_only_matching(self) -> None:
        """Фильтр inn__iexact находит вуз по ИНН."""
        target = UniversityFactory(inn="7729082090")
        UniversityFactory(inn="7701000000")

        response = self.client.get(
            path=self.list_url,
            data={"inn__iexact": "7729082090"},
        )

        # Проверяем, что найден только вуз с этим ИНН
        self.assertEqual(
            [item["id"] for item in response.data["results"]],
            [str(target.pk)],
        )

    def test_search_finds_university_by_inn(self) -> None:
        """Поиск находит вуз по ИНН."""
        target = UniversityFactory(inn="7729082090")
        UniversityFactory()

        response = self.client.get(path=self.list_url, data={"search": "7729082090"})

        # Проверяем, что поиск учитывает ИНН
        self.assertEqual(
            [item["id"] for item in response.data["results"]],
            [str(target.pk)],
        )

    def test_map_returns_only_ids_and_coordinates(self) -> None:
        """Карта получает только координаты вузов, у которых они заполнены."""
        target = UniversityFactory(lat="57.160488", lon="65.527412")
        UniversityFactory(lat=None, lon=None)
        UniversityFactory(lat="55.755864", lon=None)

        response = self.client.get(path=reverse("catalog:university-map-points"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data,
            [
                {
                    "id": str(target.pk),
                    "lat": "57.160488",
                    "lon": "65.527412",
                    "has_interactions": False,
                }
            ],
        )

    def test_map_search_returns_only_matching_university(self) -> None:
        """Поиск карты фильтрует точки по данным вуза."""
        target = UniversityFactory(
            name="Московский государственный университет",
            lat="55.703934",
            lon="37.528669",
        )
        UniversityFactory(
            name="Санкт-Петербургский государственный университет",
            lat="59.941988",
            lon="30.298918",
        )

        response = self.client.get(
            path=reverse("catalog:university-map-points"),
            data={"search": "Московский"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [item["id"] for item in response.data],
            [str(target.pk)],
        )


class B2CClientApiTestCase(BaseApiTestMixin, APITestCase):
    """Тесты CRUD /api/catalog/b2c-clients/."""

    url_basename = "catalog:b2c-client"
    model = B2CClient

    def create_instance(self, **kwargs) -> B2CClient:
        """Создаёт B2C-клиента."""
        return B2CClientFactory(**kwargs)

    def get_expected_data(self, instance: B2CClient) -> dict:
        """Поля read-представления клиента."""
        return {
            "id": str(instance.pk),
            "full_name": instance.full_name,
            "inn": instance.inn,
            "email": instance.email,
            "phone": instance.phone,
            "kind": instance.kind,
            "is_active": instance.is_active,
        }

    def get_post_data(self) -> dict:
        """Данные создания клиента."""
        return {"full_name": "ООО Ромашка", "kind": ClientKind.LEGAL_ENTITY}

    def get_change_data(self) -> dict:
        """Данные обновления клиента."""
        return {"full_name": "ИП Петров", "kind": ClientKind.INDIVIDUAL}

    def get_search_term(self, instance: B2CClient) -> str:
        """Поиск по ФИО / наименованию."""
        return instance.full_name

    def test_filter_by_kind_returns_only_matching(self) -> None:
        """Фильтр kind возвращает клиентов только указанного типа."""
        B2CClientFactory(kind=ClientKind.INDIVIDUAL)
        legal = B2CClientFactory(kind=ClientKind.LEGAL_ENTITY)

        response = self.client.get(
            path=self.list_url,
            data={"kind": ClientKind.LEGAL_ENTITY},
        )

        # Проверяем, что найден только юрлицо
        self.assertEqual(
            [item["id"] for item in response.data["results"]],
            [str(legal.pk)],
        )
