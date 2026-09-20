from datetime import datetime, timedelta, timezone

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from sova.catalog.tests.factories import (
    B2CClientFactory,
    ITDirectionFactory,
    ITProductFactory,
    ITProgramFactory,
    UniversityFactory,
)
from sova.core.tests.factories import UserFactory
from sova.core.tests.base import BaseApiTestMixin
from sova.interactions.models import Interaction
from sova.interactions.tests.factories import (
    ContractFactory,
    InteractionDirectionFactory,
    InteractionFactory,
    InteractionProductFactory,
    InteractionProgramFactory,
    ResponsibleFactory,
)


class InteractionApiTestCase(BaseApiTestMixin, APITestCase):
    """Тесты CRUD /api/interactions/interactions/."""

    url_basename = "interactions:interaction"
    model = Interaction

    def create_instance(self, **kwargs) -> Interaction:
        """Создаёт взаимодействие с вузом."""
        return InteractionFactory(**kwargs)

    def get_expected_data(self, instance: Interaction) -> dict:
        """Поля read-представления взаимодействия."""
        university = instance.university
        return {
            "id": str(instance.pk),
            "comment": instance.comment,
            "is_active": instance.is_active,
            "university": (
                {"id": str(university.pk), "name": university.name}
                if university
                else None
            ),
            "b2c_client": None,
            "current_responsible": None,
            "directions_count": 0,
            "programs_count": 0,
            "products_count": 0,
        }

    def get_post_data(self) -> dict:
        """Данные создания взаимодействия (вуз — по id)."""
        return {"comment": "Первичный контакт", "university": str(UniversityFactory().pk)}

    def get_change_data(self) -> dict:
        """Данные обновления взаимодействия."""
        return {"comment": "Обновлено", "is_active": False}

    def get_search_term(self, instance: Interaction) -> str:
        """Поиск по названию вуза."""
        return instance.university.name

    def test_add_for_b2c_client_creates_interaction(self) -> None:
        """Взаимодействие с B2C-клиентом создаётся без вуза."""
        client = B2CClientFactory()

        response = self.client.post(
            path=self.list_url,
            data={"b2c_client": str(client.pk)},
            format="json",
        )

        # Проверяем, что контрагентом выбран клиент
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.data)
        self.assertIsNone(response.data["university"])
        self.assertEqual(response.data["b2c_client"]["id"], str(client.pk))

    def test_add_returns_400_without_counterparty(self) -> None:
        """Создание без вуза и без клиента возвращает 400."""
        response = self.client.post(path=self.list_url, data={}, format="json")

        # Проверяем, что CheckConstraint не доходит до БД
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_add_returns_400_with_both_counterparties(self) -> None:
        """Создание одновременно с вузом и клиентом возвращает 400."""
        response = self.client.post(
            path=self.list_url,
            data={
                "university": str(UniversityFactory().pk),
                "b2c_client": str(B2CClientFactory().pk),
            },
            format="json",
        )

        # Проверяем, что контрагент должен быть ровно один
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_change_returns_400_when_adding_second_counterparty(self) -> None:
        """PATCH, добавляющий клиента ко взаимодействию с вузом, возвращает 400."""
        instance = InteractionFactory()

        response = self.client.patch(
            path=self.detail_url(instance),
            data={"b2c_client": str(B2CClientFactory().pk)},
            format="json",
        )

        # Проверяем, что при PATCH учитывается текущий контрагент
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_delete_returns_409_when_interaction_has_contract(self) -> None:
        """Удаление взаимодействия с договором возвращает 409 с кодом protected."""
        contract = ContractFactory()

        response = self.client.delete(path=self.detail_url(contract.interaction))

        # Проверяем, что защита PROTECT превращается в 409, а не 500
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "protected")

    def test_list_returns_counts_and_current_responsible(self) -> None:
        """В списке считаются активные направления/программы/продукты и виден ответственный."""
        interaction = InteractionFactory()
        InteractionDirectionFactory.create_batch(size=2, interaction=interaction)
        InteractionDirectionFactory(interaction=interaction, is_active=False)
        InteractionProgramFactory(interaction=interaction)
        InteractionProductFactory.create_batch(size=3, interaction=interaction)
        manager = UserFactory(first_name="Пётр", last_name="Петров")
        ResponsibleFactory(
            interaction=interaction,
            manager=manager,
            unassigned_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        current = ResponsibleFactory(interaction=interaction, manager=manager)

        response = self.client.get(path=self.list_url)
        item = response.data["results"][0]

        # Проверяем счётчики: неактивные не учитываются, join'ы не задваивают
        self.assertEqual(item["directions_count"], 2)
        self.assertEqual(item["programs_count"], 1)
        self.assertEqual(item["products_count"], 3)
        # Проверяем, что показан именно действующий ответственный
        self.assertEqual(item["current_responsible"]["id"], str(current.pk))
        self.assertEqual(
            item["current_responsible"]["manager"]["full_name"],
            "Пётр Петров",
        )

    def test_add_returns_counts_of_new_interaction(self) -> None:
        """Ответ на создание содержит аннотированные счётчики."""
        response = self.client.post(
            path=self.list_url,
            data=self.get_post_data(),
            format="json",
        )

        # Проверяем, что аннотации доступны сразу после создания
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["products_count"], 0)
        self.assertIsNone(response.data["current_responsible"])

    def assert_filter_returns(self, params: dict, expected: list[Interaction]) -> None:
        """Проверяет, что список с фильтром содержит ровно ожидаемые взаимодействия."""
        response = self.client.get(path=self.list_url, data=params)

        # Проверяем состав выдачи (порядок не важен)
        self.assertEqual(
            sorted(item["id"] for item in response.data["results"]),
            sorted(str(interaction.pk) for interaction in expected),
        )

    def test_filter_by_university_ids(self) -> None:
        """Фильтр university__ids возвращает взаимодействия указанных вузов."""
        target = InteractionFactory()
        InteractionFactory()

        self.assert_filter_returns(
            params={"university__ids": str(target.university_id)},
            expected=[target],
        )

    def test_filter_by_b2c_client_ids(self) -> None:
        """Фильтр b2c_client__ids возвращает взаимодействия указанных клиентов."""
        client = B2CClientFactory()
        target = InteractionFactory(university=None, b2c_client=client)
        InteractionFactory()

        self.assert_filter_returns(
            params={"b2c_client__ids": str(client.pk)},
            expected=[target],
        )

    def test_filter_by_it_direction_ids_ignores_inactive_links(self) -> None:
        """Фильтр it_direction__ids учитывает только активные направления."""
        direction = ITDirectionFactory()
        target = InteractionFactory()
        InteractionDirectionFactory(interaction=target, it_direction=direction)
        removed = InteractionFactory()
        InteractionDirectionFactory(
            interaction=removed,
            it_direction=direction,
            is_active=False,
        )

        self.assert_filter_returns(
            params={"it_direction__ids": str(direction.pk)},
            expected=[target],
        )

    def test_filter_by_it_program_ids(self) -> None:
        """Фильтр it_program__ids возвращает взаимодействия с указанной программой."""
        program = ITProgramFactory()
        target = InteractionFactory()
        InteractionProgramFactory(interaction=target, it_program=program)
        InteractionProgramFactory(it_program=ITProgramFactory())

        self.assert_filter_returns(
            params={"it_program__ids": str(program.pk)},
            expected=[target],
        )

    def test_filter_by_it_product_ids(self) -> None:
        """Фильтр it_product__ids возвращает взаимодействия с указанным продуктом."""
        product = ITProductFactory()
        target = InteractionFactory()
        InteractionProductFactory(interaction=target, it_product=product)
        InteractionProductFactory()

        self.assert_filter_returns(
            params={"it_product__ids": str(product.pk)},
            expected=[target],
        )

    def test_filter_by_manager_ids_uses_current_responsible_only(self) -> None:
        """Фильтр manager__ids ищет только по действующему ответственному."""
        manager = UserFactory()
        target = InteractionFactory()
        ResponsibleFactory(interaction=target, manager=manager)
        former = InteractionFactory()
        ResponsibleFactory(
            interaction=former,
            manager=manager,
            unassigned_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

        self.assert_filter_returns(
            params={"manager__ids": str(manager.pk)},
            expected=[target],
        )

    def test_filter_by_created_period(self) -> None:
        """Фильтры created_at__gte/created_at__lte ограничивают период по дате создания."""
        now = datetime.now(tz=timezone.utc)
        old = InteractionFactory()
        recent = InteractionFactory()
        Interaction.objects.filter(pk=old.pk).update(created_at=now - timedelta(days=40))
        Interaction.objects.filter(pk=recent.pk).update(created_at=now - timedelta(days=2))
        date_from = (now - timedelta(days=10)).date().isoformat()

        self.assert_filter_returns(
            params={"created_at__gte": date_from},
            expected=[recent],
        )
        self.assert_filter_returns(
            params={"created_at__lte": date_from},
            expected=[old],
        )

    def test_filter_by_is_active(self) -> None:
        """Фильтр is_active=false возвращает только неактивные взаимодействия."""
        InteractionFactory(is_active=True)
        inactive = InteractionFactory(is_active=False)

        self.assert_filter_returns(
            params={"is_active": "false"},
            expected=[inactive],
        )


class InteractionResponsibleActionsTestCase(APITestCase):
    """Тесты действий assign-responsible и unassign-responsible взаимодействия."""

    def setUp(self) -> None:
        """Аутентифицирует клиента и создаёт взаимодействие."""
        self.user = UserFactory()
        self.client.force_authenticate(user=self.user)
        self.interaction = InteractionFactory()
        self.assign_url = reverse(
            "interactions:interaction-assign-responsible",
            args=[self.interaction.pk],
        )
        self.unassign_url = reverse(
            "interactions:interaction-unassign-responsible",
            args=[self.interaction.pk],
        )

    def test_assign_creates_active_responsible(self) -> None:
        """Назначение создаёт действующую запись с assigned_by из запроса."""
        manager = UserFactory()

        response = self.client.post(
            path=self.assign_url,
            data={"manager": manager.pk},
            format="json",
        )

        # Проверяем, что запись создана
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.data)
        # Проверяем менеджера и автора назначения
        self.assertEqual(response.data["manager"]["id"], manager.pk)
        self.assertEqual(response.data["assigned_by"]["id"], self.user.pk)
        # Проверяем, что назначение действующее
        self.assertIsNone(response.data["unassigned_at"])

    def test_assign_another_manager_closes_previous_record(self) -> None:
        """Смена ответственного закрывает прежнюю запись и сохраняет историю."""
        first = ResponsibleFactory(interaction=self.interaction)
        new_manager = UserFactory()

        response = self.client.post(
            path=self.assign_url,
            data={"manager": new_manager.pk},
            format="json",
        )
        first.refresh_from_db()

        # Проверяем, что создано новое назначение
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.data)
        # Проверяем, что прежнее назначение закрыто, а не удалено
        self.assertIsNotNone(first.unassigned_at)
        self.assertEqual(self.interaction.responsibles.count(), 2)
        self.assertEqual(
            self.interaction.responsibles.filter(unassigned_at__isnull=True).count(),
            1,
        )

    def test_assign_same_manager_is_idempotent(self) -> None:
        """Повторное назначение того же менеджера возвращает 200 без новой записи."""
        current = ResponsibleFactory(interaction=self.interaction)

        response = self.client.post(
            path=self.assign_url,
            data={"manager": current.manager_id},
            format="json",
        )

        # Проверяем, что история не разрослась
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], str(current.pk))
        self.assertEqual(self.interaction.responsibles.count(), 1)

    def test_assign_returns_400_for_inactive_user(self) -> None:
        """Назначение неактивного пользователя возвращает 400."""
        manager = UserFactory(is_active=False)

        response = self.client.post(
            path=self.assign_url,
            data={"manager": manager.pk},
            format="json",
        )

        # Проверяем, что менеджер отклонён валидацией
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("manager", response.data)

    def test_unassign_closes_current_responsible(self) -> None:
        """Снятие закрывает действующую запись."""
        current = ResponsibleFactory(interaction=self.interaction)

        response = self.client.post(path=self.unassign_url)
        current.refresh_from_db()

        # Проверяем, что запись закрыта и осталась в истории
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(current.unassigned_at)
        self.assertIsNotNone(response.data["unassigned_at"])

    def test_unassign_returns_409_without_current_responsible(self) -> None:
        """Снятие при отсутствии ответственного возвращает 409."""
        response = self.client.post(path=self.unassign_url)

        # Проверяем код ошибки
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "no_active_responsible")
