from datetime import datetime, timedelta, timezone

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import SystemRole, UserRole
from sova.catalog.tests.factories import (
    B2CClientFactory,
    DirectionFactory,
    ProductFactory,
    ProgramFactory,
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
from sova.processes.enum import ActionInstanceStatus
from sova.processes.tests.factories import ActionInstanceFactory


class InteractionApiTestCase(BaseApiTestMixin, APITestCase):
    """Тесты CRUD /api/interactions/interactions/."""

    url_basename = "interactions:interaction"
    model = Interaction

    def setUp(self) -> None:
        """Даёт пользователю роль администратора платформы: выборка зависит от роли в СОВА."""
        super().setUp()
        UserRole.objects.create(user=self.user, role=SystemRole.PLATFORM_ADMIN)

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
            "current_responsibles": [],
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

    def test_list_returns_counts_and_current_responsibles(self) -> None:
        """В списке считаются активные направления/программы/продукты и видны действующие ответственные."""
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
        second = ResponsibleFactory(interaction=interaction)

        response = self.client.get(path=self.list_url)
        item = response.data["results"][0]

        # Проверяем счётчики: неактивные не учитываются, join'ы не задваивают
        self.assertEqual(item["directions_count"], 2)
        self.assertEqual(item["programs_count"], 1)
        self.assertEqual(item["products_count"], 3)
        # Проверяем, что показаны все действующие ответственные в порядке назначения, закрытые — нет
        self.assertEqual(
            [responsible["id"] for responsible in item["current_responsibles"]],
            [str(current.pk), str(second.pk)],
        )
        self.assertEqual(
            item["current_responsibles"][0]["manager"]["full_name"],
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
        self.assertEqual(response.data["current_responsibles"], [])

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

    def test_filter_by_direction_ids_ignores_inactive_links(self) -> None:
        """Фильтр direction__ids учитывает только активные направления."""
        direction = DirectionFactory()
        target = InteractionFactory()
        InteractionDirectionFactory(interaction=target, direction=direction)
        removed = InteractionFactory()
        InteractionDirectionFactory(
            interaction=removed,
            direction=direction,
            is_active=False,
        )

        self.assert_filter_returns(
            params={"direction__ids": str(direction.pk)},
            expected=[target],
        )

    def test_filter_by_program_ids(self) -> None:
        """Фильтр program__ids возвращает взаимодействия с указанной программой."""
        program = ProgramFactory()
        target = InteractionFactory()
        InteractionProgramFactory(interaction=target, program=program)
        InteractionProgramFactory(program=ProgramFactory())

        self.assert_filter_returns(
            params={"program__ids": str(program.pk)},
            expected=[target],
        )

    def test_filter_by_product_ids(self) -> None:
        """Фильтр product__ids возвращает взаимодействия с указанным продуктом."""
        product = ProductFactory()
        target = InteractionFactory()
        InteractionProductFactory(interaction=target, product=product)
        InteractionProductFactory()

        self.assert_filter_returns(
            params={"product__ids": str(product.pk)},
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
        """Аутентифицирует клиента администратором платформы и создаёт взаимодействие."""
        self.user = UserFactory()
        UserRole.objects.create(user=self.user, role=SystemRole.PLATFORM_ADMIN)
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

    def test_assign_another_manager_keeps_current(self) -> None:
        """Назначение второго менеджера добавляет КАМа, действующий остаётся."""
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
        # Проверяем, что прежнее назначение не закрыто — у взаимодействия два действующих КАМа
        self.assertIsNone(first.unassigned_at)
        self.assertEqual(
            self.interaction.responsibles.filter(unassigned_at__isnull=True).count(),
            2,
        )

    def test_assign_does_not_touch_open_actions(self) -> None:
        """Назначение не переносит открытые действия: действия из пула остаются без ответственного."""
        first = ResponsibleFactory(interaction=self.interaction)
        pool = ActionInstanceFactory(
            stage_instance__workflow_instance__interaction=self.interaction,
            status=ActionInstanceStatus.PENDING,
            responsible=None,
        )
        owned = ActionInstanceFactory(
            stage_instance__workflow_instance__interaction=self.interaction,
            status=ActionInstanceStatus.IN_PROGRESS,
            responsible=first.manager,
        )

        response = self.client.post(
            path=self.assign_url,
            data={"manager": UserFactory().pk},
            format="json",
        )
        pool.refresh_from_db()
        owned.refresh_from_db()

        # Проверяем, что назначение прошло
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.data)
        # Проверяем, что действия остались при своих ответственных
        self.assertIsNone(pool.responsible_id)
        self.assertEqual(owned.responsible_id, first.manager_id)

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

        response = self.client.post(path=self.unassign_url, data={"manager": current.manager_id}, format="json")
        current.refresh_from_db()

        # Проверяем, что запись закрыта и осталась в истории
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(current.unassigned_at)
        self.assertIsNotNone(response.data["unassigned_at"])

    def test_unassign_releases_open_actions_of_the_manager(self) -> None:
        """Снятие обнуляет ответственного у открытых действий снятого менеджера, завершённые не трогает."""
        current = ResponsibleFactory(interaction=self.interaction)
        in_progress = ActionInstanceFactory(
            stage_instance__workflow_instance__interaction=self.interaction,
            status=ActionInstanceStatus.IN_PROGRESS,
            responsible=current.manager,
        )
        pending = ActionInstanceFactory(
            stage_instance__workflow_instance__interaction=self.interaction,
            status=ActionInstanceStatus.PENDING,
            responsible=current.manager,
        )
        completed = ActionInstanceFactory(
            stage_instance__workflow_instance__interaction=self.interaction,
            status=ActionInstanceStatus.COMPLETED,
            responsible=current.manager,
        )
        foreign = ActionInstanceFactory(status=ActionInstanceStatus.IN_PROGRESS, responsible=current.manager)

        response = self.client.post(path=self.unassign_url, data={"manager": current.manager_id}, format="json")
        for instance in (in_progress, pending, completed, foreign):
            instance.refresh_from_db()

        # Проверяем, что снятие прошло успешно
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Проверяем, что открытые действия взаимодействия остались без ответственного
        self.assertIsNone(in_progress.responsible_id)
        self.assertIsNone(pending.responsible_id)
        # Проверяем, что завершённое исполнение сохранило ответственного в истории
        self.assertEqual(completed.responsible_id, current.manager_id)
        # Проверяем, что действия другого взаимодействия не затронуты
        self.assertEqual(foreign.responsible_id, current.manager_id)

    def test_unassign_one_of_two_keeps_the_other(self) -> None:
        """Снятие одного из двух КАМов закрывает только его запись, действия второго не трогает."""
        leaving = ResponsibleFactory(interaction=self.interaction)
        staying = ResponsibleFactory(interaction=self.interaction)
        staying_action = ActionInstanceFactory(
            stage_instance__workflow_instance__interaction=self.interaction,
            status=ActionInstanceStatus.PENDING,
            responsible=staying.manager,
        )

        response = self.client.post(path=self.unassign_url, data={"manager": leaving.manager_id}, format="json")
        leaving.refresh_from_db()
        staying.refresh_from_db()
        staying_action.refresh_from_db()

        # Проверяем, что снят указанный менеджер
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], str(leaving.pk))
        self.assertIsNotNone(leaving.unassigned_at)
        # Проверяем, что второй КАМ и его действие остались
        self.assertIsNone(staying.unassigned_at)
        self.assertEqual(staying_action.responsible_id, staying.manager_id)

    def test_unassign_returns_400_without_manager(self) -> None:
        """Снятие без указания менеджера возвращает 400."""
        ResponsibleFactory(interaction=self.interaction)

        response = self.client.post(path=self.unassign_url, data={}, format="json")

        # Проверяем, что менеджер обязателен
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("manager", response.data)

    def test_unassign_returns_409_for_not_assigned_manager(self) -> None:
        """Снятие менеджера, который не назначен на взаимодействие, возвращает 409."""
        ResponsibleFactory(interaction=self.interaction)

        response = self.client.post(path=self.unassign_url, data={"manager": UserFactory().pk}, format="json")

        # Проверяем код ошибки
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "no_active_responsible")

    def test_unassign_returns_409_without_current_responsible(self) -> None:
        """Снятие при отсутствии ответственного возвращает 409."""
        response = self.client.post(path=self.unassign_url, data={"manager": UserFactory().pk}, format="json")

        # Проверяем код ошибки
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "no_active_responsible")
