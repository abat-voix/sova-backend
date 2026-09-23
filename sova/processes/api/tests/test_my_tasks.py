from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import SystemRole, UserRole
from sova.core.tests.factories import UserFactory
from sova.interactions.services import responsible_service
from sova.interactions.tests.factories import InteractionFactory
from sova.processes.models import ActionInstance
from sova.processes.tests.base import EngineApiTestCase
from sova.processes.tests.factories import ActionAttachmentFactory, ActionInstanceFactory

LIST_URL = reverse("processes:action-instance-list")


class ActionInstanceCardTestCase(EngineApiTestCase):
    """Тесты состава карточки действия в /api/processes/action-instances/ — экран «Мои задачи»."""

    def card(self, params: dict | None = None) -> dict:
        """Первая карточка списка со всеми доступными действиями."""
        response = self.client.get(path=LIST_URL, data={"scope": "all", **(params or {})})

        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
        self.assertEqual(response.data["count"], 1, msg=response.data)
        return response.data["results"][0]

    def test_card_carries_everything_the_board_shows(self) -> None:
        """Карточка отдаёт этап, взаимодействие, процесс и исходы — тем же составом, что доска."""
        stage = self.builder.stage("Согласование и документы")
        action = self.builder.action(stage, "Подписать договор", duration_days=7)

        process = self.start()

        card = self.card()
        instance = self.action_instance(process, action)
        self.assertEqual(card["id"], str(instance.pk))
        self.assertEqual(card["stage_name_snapshot"], stage.name)
        self.assertEqual(card["workflow_instance"], str(process.pk))
        self.assertEqual(card["interaction"]["id"], str(self.interaction.pk))
        self.assertEqual(card["interaction"]["university"]["id"], str(self.interaction.university_id))
        self.assertEqual(card["attachments_count"], 0)
        self.assertFalse(card["is_optional"])
        self.assertFalse(card["is_trigger_only"])
        self.assertFalse(card["is_overdue"])
        self.assertIsNone(card["result"])
        # Действие в работе: на карточке есть кнопки исходов
        self.assertEqual([outcome["code"] for outcome in card["available_outcomes"]], ["done"])
        self.assertEqual(
            set(card["available_outcomes"][0]),
            {"id", "code", "name", "is_comment_required", "is_attachment_required"},
        )

    def test_pending_action_has_no_outcomes(self) -> None:
        """У действия не в работе кнопок исходов нет — как на доске."""
        first = self.builder.stage("Первый")
        self.builder.action(first, "А")
        second = self.builder.stage("Второй", after=(first,))
        later = self.builder.action(second, "Б")

        process = self.start()

        card = self.card({"action__ids": str(later.pk)})
        self.assertEqual(card["status"], "pending")
        self.assertEqual(card["available_outcomes"], [])

    def test_completed_action_carries_its_result(self) -> None:
        """В колонке «Завершено» видно исход и комментарий."""
        stage = self.builder.stage("Первый")
        action = self.builder.action(stage, "А")

        process = self.start()
        self.complete(process, action, comment="Готово")

        card = self.card()
        self.assertEqual(card["status"], "completed")
        self.assertEqual(card["result"]["outcome_name"], "Выполнено")
        self.assertEqual(card["result"]["comment"], "Готово")
        self.assertEqual(card["result"]["created_by"]["id"], self.user.pk)
        self.assertEqual(card["available_outcomes"], [])

    def test_overdue_action_is_marked(self) -> None:
        """Невыполненное действие с прошедшим плановым окончанием помечено просроченным."""
        stage = self.builder.stage("Первый")
        action = self.builder.action(stage, "А")

        process = self.start()
        ActionInstance.objects.filter(pk=self.action_instance(process, action).pk).update(
            planned_end=timezone.now() - timedelta(days=1),
        )

        self.assertTrue(self.card()["is_overdue"])

    def test_attachments_are_counted(self) -> None:
        """Число вложений на карточке — чтобы форма не просила файл повторно."""
        stage = self.builder.stage("Первый")
        action = self.builder.action(stage, "А")

        process = self.start()
        ActionAttachmentFactory(action_instance=self.action_instance(process, action))

        self.assertEqual(self.card()["attachments_count"], 1)


class MyTasksScopeTestCase(APITestCase):
    """Тесты параметра scope и ролевой видимости действий."""

    @staticmethod
    def create_user(role: str):
        """Создаёт пользователя с ролью СОВА."""
        user = UserFactory()
        UserRole.objects.create(user=user, role=role)
        return user

    @staticmethod
    def create_action(manager=None, responsible=None) -> ActionInstance:
        """Создаёт действие во взаимодействии менеджера `manager` с исполнителем `responsible`."""
        interaction = InteractionFactory()
        if manager is not None:
            responsible_service.assign(interaction=interaction, manager=manager, assigned_by=None)
        instance = ActionInstanceFactory(responsible=responsible)
        instance.stage_instance.workflow_instance.interaction = interaction
        instance.stage_instance.workflow_instance.save(update_fields=["interaction"])
        return instance

    def response_ids(self, params: dict | None = None) -> set[str]:
        """Идентификаторы действий из списка."""
        response = self.client.get(path=LIST_URL, data=params)

        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
        return {item["id"] for item in response.data["results"]}

    def test_default_scope_returns_only_own_actions(self) -> None:
        """Без параметра список показывает действия, где пользователь ответственный."""
        kam = self.create_user(SystemRole.KAM)
        own = self.create_action(manager=kam, responsible=kam)
        self.create_action(manager=kam, responsible=UserFactory())
        self.client.force_authenticate(user=kam)

        self.assertEqual(self.response_ids(), {str(own.pk)})
        self.assertEqual(self.response_ids({"scope": "mine"}), {str(own.pk)})

    def test_scope_all_returns_everything_available_to_the_kam(self) -> None:
        """scope=all у КАМа не расширяет выдачу за пределы его взаимодействий, а не отклоняется."""
        kam = self.create_user(SystemRole.KAM)
        own = self.create_action(manager=kam, responsible=kam)
        colleague = self.create_action(manager=kam, responsible=UserFactory())
        foreign = self.create_action(manager=self.create_user(SystemRole.KAM))
        self.client.force_authenticate(user=kam)

        visible = self.response_ids({"scope": "all"})
        self.assertEqual(visible, {str(own.pk), str(colleague.pk)})
        self.assertNotIn(str(foreign.pk), visible)

    def test_head_sees_actions_of_kams(self) -> None:
        """Руководитель со scope=all видит действия взаимодействий КАМов."""
        head = self.create_user(SystemRole.HEAD)
        kam_action = self.create_action(manager=self.create_user(SystemRole.KAM))
        own = self.create_action(manager=head, responsible=head)
        self.client.force_authenticate(user=head)

        self.assertEqual(self.response_ids({"scope": "all"}), {str(kam_action.pk), str(own.pk)})
        self.assertEqual(self.response_ids(), {str(own.pk)})

    def test_foreign_action_is_not_retrievable(self) -> None:
        """Действие чужого взаимодействия недоступно и по прямой ссылке."""
        kam = self.create_user(SystemRole.KAM)
        foreign = self.create_action(manager=self.create_user(SystemRole.KAM))
        self.client.force_authenticate(user=kam)

        response = self.client.get(path=reverse("processes:action-instance-detail", args=(foreign.pk,)))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_own_action_is_retrievable_regardless_of_scope(self) -> None:
        """Действие коллеги по своему взаимодействию открывается по ссылке: scope сужает только список."""
        kam = self.create_user(SystemRole.KAM)
        colleague = self.create_action(manager=kam, responsible=UserFactory())
        self.client.force_authenticate(user=kam)

        response = self.client.get(path=reverse("processes:action-instance-detail", args=(colleague.pk,)))

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_unknown_scope_is_rejected(self) -> None:
        """Неизвестное значение scope отклоняется с 400."""
        kam = self.create_user(SystemRole.KAM)
        self.client.force_authenticate(user=kam)

        response = self.client.get(path=LIST_URL, data={"scope": "everything"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class MyTasksFilterTestCase(APITestCase):
    """Тесты фильтров экрана: взаимодействие, дата завершения и сортировка."""

    def setUp(self) -> None:
        """Аутентифицирует администратора платформы: видимость здесь не проверяется."""
        self.user = UserFactory()
        UserRole.objects.create(user=self.user, role=SystemRole.PLATFORM_ADMIN)
        self.client.force_authenticate(user=self.user)

    def response_ids(self, params: dict) -> list[str]:
        """Идентификаторы действий из списка, в порядке ответа."""
        response = self.client.get(path=LIST_URL, data={"scope": "all", **params})

        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
        return [item["id"] for item in response.data["results"]]

    def test_filters_by_interaction(self) -> None:
        """Фильтр по взаимодействию берёт действия всех его процессов."""
        target = ActionInstanceFactory()
        interaction = target.stage_instance.workflow_instance.interaction
        ActionInstanceFactory()

        self.assertEqual(
            self.response_ids({"interaction__ids": str(interaction.pk)}),
            [str(target.pk)],
        )

    def test_filters_by_completion_date(self) -> None:
        """Фильтр по дате завершения ограничивает колонку «Завершено» окном."""
        now = timezone.now()
        recent = ActionInstanceFactory(status="completed", actual_end=now)
        ActionInstanceFactory(status="completed", actual_end=now - timedelta(days=40))

        self.assertEqual(
            self.response_ids({"actual_end__gte": (now - timedelta(days=30)).date().isoformat()}),
            [str(recent.pk)],
        )

    def test_orders_by_planned_end(self) -> None:
        """Сортировка по плановому окончанию работает в обе стороны."""
        now = timezone.now()
        early = ActionInstanceFactory(planned_end=now)
        late = ActionInstanceFactory(planned_end=now + timedelta(days=1))

        self.assertEqual(self.response_ids({"ordering": "planned_end"}), [str(early.pk), str(late.pk)])
        self.assertEqual(self.response_ids({"ordering": "-planned_end"}), [str(late.pk), str(early.pk)])
