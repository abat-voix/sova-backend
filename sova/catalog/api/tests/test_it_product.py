from rest_framework import status
from rest_framework.test import APITestCase

from sova.catalog.models import ITProduct
from sova.catalog.tests.factories import (
    ITDirectionFactory,
    ITProductFactory,
    ITProgramFactory,
    VendorFactory,
)
from sova.core.tests.base import BaseApiTestMixin


class ITProductApiTestCase(BaseApiTestMixin, APITestCase):
    """Тесты CRUD /api/catalog/it-products/."""

    url_basename = "catalog:it-product"
    model = ITProduct

    def create_instance(self, **kwargs) -> ITProduct:
        """Создаёт ИТ-продукт с одной программой."""
        kwargs.setdefault("programs", [ITProgramFactory()])
        return ITProductFactory(**kwargs)

    def get_expected_data(self, instance: ITProduct) -> dict:
        """Поля read-представления продукта."""
        return {
            "id": str(instance.pk),
            "name": instance.name,
            "external_code": instance.external_code,
            "is_active": instance.is_active,
            "vendor": {"id": str(instance.vendor_id), "name": instance.vendor.name},
            "programs": [
                {"id": str(program.pk), "name": program.name}
                for program in instance.programs.all()
            ],
        }

    def get_post_data(self) -> dict:
        """Данные создания продукта (вендор и программы — по id)."""
        return {
            "name": "PyCharm",
            "vendor": str(VendorFactory().pk),
            "programs": [str(ITProgramFactory().pk)],
        }

    def get_change_data(self) -> dict:
        """Данные обновления продукта."""
        return {"name": "IntelliJ IDEA", "programs": [str(ITProgramFactory().pk)]}

    def get_search_term(self, instance: ITProduct) -> str:
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
        product = ITProductFactory(name="Дубль")

        response = self.client.post(
            path=self.list_url,
            data={"name": "Дубль", "vendor": str(product.vendor_id)},
            format="json",
        )

        # Проверяем, что нарушение unique_product_per_vendor отдано как 400
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_add_returns_400_with_duplicate_name_without_vendor(self) -> None:
        """Повтор названия среди продуктов без вендора возвращает 400."""
        ITProductFactory(name="Дубль", vendor=None)

        response = self.client.post(
            path=self.list_url,
            data={"name": "Дубль"},
            format="json",
        )

        # Проверяем, что условное ограничение unique_product_without_vendor
        # ловится валидацией, а не превращается в 409
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_filter_by_it_direction_ids_uses_programs_transitively(self) -> None:
        """Фильтр it_direction__ids находит продукты через направления их программ."""
        direction = ITDirectionFactory()
        target = ITProductFactory(
            programs=[
                ITProgramFactory(it_direction=direction),
                ITProgramFactory(it_direction=direction),
            ],
        )
        ITProductFactory(programs=[ITProgramFactory()])

        response = self.client.get(
            path=self.list_url,
            data={"it_direction__ids": str(direction.pk)},
        )

        # Проверяем, что продукт с двумя программами направления не задваивается
        self.assertEqual(
            [item["id"] for item in response.data["results"]],
            [str(target.pk)],
        )

    def test_filter_by_vendor_ids_returns_only_matching(self) -> None:
        """Фильтр vendor__ids возвращает продукты указанных вендоров."""
        target = ITProductFactory()
        ITProductFactory()

        response = self.client.get(
            path=self.list_url,
            data={"vendor__ids": str(target.vendor_id)},
        )

        # Проверяем, что найден только продукт выбранного вендора
        self.assertEqual(
            [item["id"] for item in response.data["results"]],
            [str(target.pk)],
        )

    def test_filter_by_it_program_ids_returns_only_matching(self) -> None:
        """Фильтр it_program__ids возвращает продукты указанных программ."""
        program = ITProgramFactory()
        target = ITProductFactory(programs=[program])
        ITProductFactory(programs=[ITProgramFactory()])

        response = self.client.get(
            path=self.list_url,
            data={"it_program__ids": str(program.pk)},
        )

        # Проверяем, что найден только продукт выбранной программы
        self.assertEqual(
            [item["id"] for item in response.data["results"]],
            [str(target.pk)],
        )
