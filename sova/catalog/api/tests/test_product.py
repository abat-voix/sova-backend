from rest_framework import status
from rest_framework.test import APITestCase

from sova.catalog.models import Product
from sova.catalog.tests.factories import (
    DirectionFactory,
    ProductFactory,
    ProgramFactory,
    VendorFactory,
)
from sova.core.tests.base import BaseApiTestMixin


class ProductApiTestCase(BaseApiTestMixin, APITestCase):
    """Тесты CRUD /api/catalog/products/."""

    url_basename = "catalog:product"
    model = Product

    def create_instance(self, **kwargs) -> Product:
        """Создаёт продукт с одной программой."""
        kwargs.setdefault("programs", [ProgramFactory()])
        return ProductFactory(**kwargs)

    def get_expected_data(self, instance: Product) -> dict:
        """Поля read-представления продукта."""
        return {
            "id": str(instance.pk),
            "name": instance.name,
            "external_code": instance.external_code,
            "is_active": instance.is_active,
            "vendor": {"id": str(instance.vendor_id), "name": instance.vendor.name},
            # Программа с направлением: тёзки из разных направлений различимы
            "programs": [
                {
                    "id": str(program.pk),
                    "name": program.name,
                    "direction": {"id": str(program.direction_id), "name": program.direction.name},
                }
                for program in instance.programs.all()
            ],
        }

    def get_post_data(self) -> dict:
        """Данные создания продукта (вендор и программы — по id)."""
        return {
            "name": "PyCharm",
            "vendor": str(VendorFactory().pk),
            "programs": [str(ProgramFactory().pk)],
        }

    def get_change_data(self) -> dict:
        """Данные обновления продукта."""
        return {"name": "IntelliJ IDEA", "programs": [str(ProgramFactory().pk)]}

    def get_search_term(self, instance: Product) -> str:
        """Поиск по названию."""
        return instance.name

    def test_add_without_vendor_creates_product(self) -> None:
        """Продукт без вендора создаётся: vendor необязателен."""
        response = self.client.post(
            path=self.list_url,
            data={"name": "Без вендора"},
            format="json",
        )

        # Проверяем, что продукт создан, а вендор пуст
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.data)
        self.assertIsNone(response.data["vendor"])
        self.assertEqual(response.data["programs"], [])

    def test_add_returns_400_with_duplicate_name_for_vendor(self) -> None:
        """Повтор названия продукта у того же вендора возвращает 400."""
        product = ProductFactory(name="Дубль")

        response = self.client.post(
            path=self.list_url,
            data={"name": "Дубль", "vendor": str(product.vendor_id)},
            format="json",
        )

        # Проверяем, что нарушение unique_product_per_vendor отдано как 400
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_add_returns_400_with_duplicate_name_without_vendor(self) -> None:
        """Повтор названия среди продуктов без вендора возвращает 400."""
        ProductFactory(name="Дубль", vendor=None)

        response = self.client.post(
            path=self.list_url,
            data={"name": "Дубль"},
            format="json",
        )

        # Проверяем, что условное ограничение unique_product_without_vendor
        # ловится валидацией, а не превращается в 409
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_filter_by_direction_ids_uses_programs_transitively(self) -> None:
        """Фильтр direction__ids находит продукты через направления их программ."""
        direction = DirectionFactory()
        target = ProductFactory(
            programs=[
                ProgramFactory(direction=direction),
                ProgramFactory(direction=direction),
            ],
        )
        ProductFactory(programs=[ProgramFactory()])

        response = self.client.get(
            path=self.list_url,
            data={"direction__ids": str(direction.pk)},
        )

        # Проверяем, что продукт с двумя программами направления не задваивается
        self.assertEqual(
            [item["id"] for item in response.data["results"]],
            [str(target.pk)],
        )

    def test_filter_by_vendor_ids_returns_only_matching(self) -> None:
        """Фильтр vendor__ids возвращает продукты указанных вендоров."""
        target = ProductFactory()
        ProductFactory()

        response = self.client.get(
            path=self.list_url,
            data={"vendor__ids": str(target.vendor_id)},
        )

        # Проверяем, что найден только продукт выбранного вендора
        self.assertEqual(
            [item["id"] for item in response.data["results"]],
            [str(target.pk)],
        )

    def test_filter_by_program_ids_returns_only_matching(self) -> None:
        """Фильтр program__ids возвращает продукты указанных программ."""
        program = ProgramFactory()
        target = ProductFactory(programs=[program])
        ProductFactory(programs=[ProgramFactory()])

        response = self.client.get(
            path=self.list_url,
            data={"program__ids": str(program.pk)},
        )

        # Проверяем, что найден только продукт выбранной программы
        self.assertEqual(
            [item["id"] for item in response.data["results"]],
            [str(target.pk)],
        )
