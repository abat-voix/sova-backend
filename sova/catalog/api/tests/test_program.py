from rest_framework import status
from rest_framework.test import APITestCase

from sova.catalog.models import Program
from sova.catalog.tests.factories import (
    DirectionFactory,
    ProductFactory,
    ProgramFactory,
)
from sova.core.tests.base import BaseApiTestMixin


class ProgramApiTestCase(BaseApiTestMixin, APITestCase):
    """Тесты CRUD /api/catalog/programs/."""

    url_basename = "catalog:program"
    model = Program

    def create_instance(self, **kwargs) -> Program:
        """Создаёт программу."""
        return ProgramFactory(**kwargs)

    def get_expected_data(self, instance: Program) -> dict:
        """Поля read-представления программы."""
        return {
            "id": str(instance.pk),
            "name": instance.name,
            "is_active": instance.is_active,
            "direction": {
                "id": str(instance.direction_id),
                "name": instance.direction.name,
            },
            "products_count": instance.products.count(),
        }

    def get_post_data(self) -> dict:
        """Данные создания программы (направление — по id)."""
        return {
            "name": "Основы DevOps",
            "direction": str(DirectionFactory().pk),
        }

    def get_change_data(self) -> dict:
        """Данные обновления программы."""
        return {"name": "Основы QA", "direction": str(DirectionFactory().pk)}

    def get_search_term(self, instance: Program) -> str:
        """Поиск по названию."""
        return instance.name

    def test_list_counts_products(self) -> None:
        """products_count в списке равен числу продуктов программы."""
        program = ProgramFactory()
        ProductFactory.create_batch(size=2, programs=[program])

        response = self.client.get(path=self.list_url)

        # Проверяем, что счётчик посчитан аннотацией без дублей
        self.assertEqual(response.data["results"][0]["products_count"], 2)

    def test_add_returns_products_count_of_new_program(self) -> None:
        """Ответ на создание содержит аннотированный products_count."""
        response = self.client.post(
            path=self.list_url,
            data=self.get_post_data(),
            format="json",
        )

        # Проверяем, что новая программа отдана вместе с аннотацией
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["products_count"], 0)

    def test_filter_by_direction_ids_returns_only_matching(self) -> None:
        """Фильтр direction__ids возвращает программы указанных направлений."""
        target = ProgramFactory()
        ProgramFactory()

        response = self.client.get(
            path=self.list_url,
            data={"direction__ids": str(target.direction_id)},
        )

        # Проверяем, что найдена только программа выбранного направления
        self.assertEqual(
            [item["id"] for item in response.data["results"]],
            [str(target.pk)],
        )

    def test_filter_has_products_returns_only_programs_with_products(self) -> None:
        """Фильтр has_products=true возвращает только программы с продуктами."""
        with_products = ProgramFactory()
        ProgramFactory()
        ProductFactory.create_batch(size=2, programs=[with_products])

        response = self.client.get(path=self.list_url, data={"has_products": "true"})

        # Проверяем, что программа с двумя продуктами не задваивается
        self.assertEqual(
            [item["id"] for item in response.data["results"]],
            [str(with_products.pk)],
        )
