from rest_framework import status
from rest_framework.test import APITestCase

from sova.catalog.tests.factories import (
    ITDirectionFactory,
    ITProductFactory,
    ITProgramFactory,
)
from sova.core.tests.base import BaseApiTestMixin
from sova.interactions.models import (
    InteractionDirection,
    InteractionProduct,
    InteractionProgram,
)
from sova.interactions.tests.factories import (
    InteractionDirectionFactory,
    InteractionFactory,
    InteractionProductFactory,
    InteractionProgramFactory,
)


class InteractionDirectionApiTestCase(BaseApiTestMixin, APITestCase):
    """Тесты CRUD /api/interactions/interaction-directions/."""

    url_basename = "interactions:interaction-direction"
    model = InteractionDirection

    def create_instance(self, **kwargs) -> InteractionDirection:
        """Создаёт направление взаимодействия."""
        return InteractionDirectionFactory(**kwargs)

    def get_expected_data(self, instance: InteractionDirection) -> dict:
        """Поля read-представления направления взаимодействия."""
        return {
            "id": str(instance.pk),
            "interaction": str(instance.interaction_id),
            "is_active": instance.is_active,
            "it_direction": {
                "id": str(instance.it_direction_id),
                "name": instance.it_direction.name,
            },
        }

    def get_post_data(self) -> dict:
        """Данные создания (взаимодействие и направление — по id)."""
        return {
            "interaction": str(InteractionFactory().pk),
            "it_direction": str(ITDirectionFactory().pk),
        }

    def get_change_data(self) -> dict:
        """Данные обновления."""
        return {"is_active": False}

    def test_add_returns_400_with_duplicate_direction(self) -> None:
        """Повторное добавление направления во взаимодействие возвращает 400."""
        existing = InteractionDirectionFactory()

        response = self.client.post(
            path=self.list_url,
            data={
                "interaction": str(existing.interaction_id),
                "it_direction": str(existing.it_direction_id),
            },
            format="json",
        )

        # Проверяем, что нарушение unique_direction_per_interaction отдано как 400
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_filter_by_interaction_ids(self) -> None:
        """Фильтр interaction__ids возвращает направления указанных взаимодействий."""
        target = InteractionDirectionFactory()
        InteractionDirectionFactory()

        response = self.client.get(
            path=self.list_url,
            data={"interaction__ids": str(target.interaction_id)},
        )

        # Проверяем, что найдено только направление выбранного взаимодействия
        self.assertEqual(
            [item["id"] for item in response.data["results"]],
            [str(target.pk)],
        )


class InteractionProgramApiTestCase(BaseApiTestMixin, APITestCase):
    """Тесты CRUD /api/interactions/interaction-programs/."""

    url_basename = "interactions:interaction-program"
    model = InteractionProgram

    def create_instance(self, **kwargs) -> InteractionProgram:
        """Создаёт программу взаимодействия."""
        return InteractionProgramFactory(**kwargs)

    def get_expected_data(self, instance: InteractionProgram) -> dict:
        """Поля read-представления программы взаимодействия."""
        return {
            "id": str(instance.pk),
            "interaction": str(instance.interaction_id),
            "is_active": instance.is_active,
            "it_program": {
                "id": str(instance.it_program_id),
                "name": instance.it_program.name,
            },
        }

    def get_post_data(self) -> dict:
        """Данные создания (взаимодействие и программа — по id)."""
        return {
            "interaction": str(InteractionFactory().pk),
            "it_program": str(ITProgramFactory().pk),
        }

    def get_change_data(self) -> dict:
        """Данные обновления."""
        return {"is_active": False}

    def test_filter_by_it_direction_ids_uses_program_direction(self) -> None:
        """Фильтр it_direction__ids находит программы по направлению каталожной программы."""
        direction = ITDirectionFactory()
        target = InteractionProgramFactory(
            it_program=ITProgramFactory(it_direction=direction),
        )
        InteractionProgramFactory()

        response = self.client.get(
            path=self.list_url,
            data={"it_direction__ids": str(direction.pk)},
        )

        # Проверяем, что направление выводится через it_program.it_direction
        self.assertEqual(
            [item["id"] for item in response.data["results"]],
            [str(target.pk)],
        )

    def test_filter_by_interaction_ids(self) -> None:
        """Фильтр interaction__ids возвращает программы указанных взаимодействий."""
        target = InteractionProgramFactory()
        InteractionProgramFactory()

        response = self.client.get(
            path=self.list_url,
            data={"interaction__ids": str(target.interaction_id)},
        )

        # Проверяем, что найдена только программа выбранного взаимодействия
        self.assertEqual(
            [item["id"] for item in response.data["results"]],
            [str(target.pk)],
        )


class InteractionProductApiTestCase(BaseApiTestMixin, APITestCase):
    """Тесты CRUD /api/interactions/interaction-products/."""

    url_basename = "interactions:interaction-product"
    model = InteractionProduct

    def create_instance(self, **kwargs) -> InteractionProduct:
        """Создаёт продукт взаимодействия без программы."""
        return InteractionProductFactory(**kwargs)

    def get_expected_data(self, instance: InteractionProduct) -> dict:
        """Поля read-представления продукта взаимодействия."""
        return {
            "id": str(instance.pk),
            "interaction": str(instance.interaction_id),
            "interaction_program": None,
            "is_active": instance.is_active,
            "it_product": {
                "id": str(instance.it_product_id),
                "name": instance.it_product.name,
            },
        }

    def get_post_data(self) -> dict:
        """Данные создания (взаимодействие и продукт — по id)."""
        return {
            "interaction": str(InteractionFactory().pk),
            "it_product": str(ITProductFactory().pk),
        }

    def get_change_data(self) -> dict:
        """Данные обновления."""
        return {"is_active": False}

    def test_add_with_program_of_same_interaction_creates_product(self) -> None:
        """Продукт из каталога программы создаётся с привязкой к ней."""
        program_link = InteractionProgramFactory()
        product = ITProductFactory(programs=[program_link.it_program])

        response = self.client.post(
            path=self.list_url,
            data={
                "interaction": str(program_link.interaction_id),
                "interaction_program": str(program_link.pk),
                "it_product": str(product.pk),
            },
            format="json",
        )

        # Проверяем, что связь с программой взаимодействия сохранена
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.data)
        self.assertEqual(str(response.data["interaction_program"]), str(program_link.pk))

    def test_add_returns_400_with_program_of_another_interaction(self) -> None:
        """Программа другого взаимодействия отклоняется (InteractionProduct.clean)."""
        program_link = InteractionProgramFactory()
        product = ITProductFactory(programs=[program_link.it_program])

        response = self.client.post(
            path=self.list_url,
            data={
                "interaction": str(InteractionFactory().pk),
                "interaction_program": str(program_link.pk),
                "it_product": str(product.pk),
            },
            format="json",
        )

        # Проверяем, что ошибка привязана к полю interaction_program
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("interaction_program", response.data)

    def test_add_returns_400_with_product_outside_program_catalog(self) -> None:
        """Продукт, не входящий в каталог программы, отклоняется."""
        program_link = InteractionProgramFactory()

        response = self.client.post(
            path=self.list_url,
            data={
                "interaction": str(program_link.interaction_id),
                "interaction_program": str(program_link.pk),
                "it_product": str(ITProductFactory().pk),
            },
            format="json",
        )

        # Проверяем, что ошибка привязана к полю it_product
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("it_product", response.data)

    def test_change_returns_400_when_program_switched_to_foreign(self) -> None:
        """PATCH, привязывающий программу другого взаимодействия, возвращает 400."""
        instance = InteractionProductFactory()
        foreign = InteractionProgramFactory()

        response = self.client.patch(
            path=self.detail_url(instance),
            data={"interaction_program": str(foreign.pk)},
            format="json",
        )

        # Проверяем, что clean() отрабатывает и при частичном обновлении
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_add_returns_400_with_duplicate_product(self) -> None:
        """Повторное добавление продукта во взаимодействие возвращает 400."""
        existing = InteractionProductFactory()

        response = self.client.post(
            path=self.list_url,
            data={
                "interaction": str(existing.interaction_id),
                "it_product": str(existing.it_product_id),
            },
            format="json",
        )

        # Проверяем, что нарушение unique_product_per_interaction отдано как 400
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_filter_by_it_direction_ids_uses_product_programs(self) -> None:
        """Фильтр it_direction__ids находит продукты через программы каталога."""
        direction = ITDirectionFactory()
        product = ITProductFactory(
            programs=[
                ITProgramFactory(it_direction=direction),
                ITProgramFactory(it_direction=direction),
            ],
        )
        target = InteractionProductFactory(it_product=product)
        InteractionProductFactory()

        response = self.client.get(
            path=self.list_url,
            data={"it_direction__ids": str(direction.pk)},
        )

        # Проверяем, что продукт с двумя программами направления не задваивается
        self.assertEqual(
            [item["id"] for item in response.data["results"]],
            [str(target.pk)],
        )

    def test_filter_by_it_product_ids(self) -> None:
        """Фильтр it_product__ids возвращает записи с указанным продуктом."""
        target = InteractionProductFactory()
        InteractionProductFactory()

        response = self.client.get(
            path=self.list_url,
            data={"it_product__ids": str(target.it_product_id)},
        )

        # Проверяем, что найдена только запись выбранного продукта
        self.assertEqual(
            [item["id"] for item in response.data["results"]],
            [str(target.pk)],
        )
