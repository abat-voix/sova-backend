from datetime import timedelta

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from sova.interactions.tests.factories import (
    InteractionDirectionFactory,
    InteractionProductFactory,
    InteractionProgramFactory,
)
from sova.processes.enum import StageInstanceStatus
from sova.processes.models import ActionInstance
from sova.processes.services import workflow_board_service as board_service
from sova.processes.tests.base import (
    COMPLETED,
    DIRECTION,
    IN_PROGRESS,
    PENDING,
    PRODUCT,
    PROGRAM,
    EngineTestCase,
)
from sova.processes.tests.factories import ActionAttachmentFactory


class BoardTest(EngineTestCase):
    """Тесты доски процесса: всё для визуализации пути взаимодействия одним объектом."""

    def setUp(self) -> None:
        """Два этапа взаимодействия: в первом обязательное и необязательное действия, во втором одно."""
        super().setUp()
        self.first = self.builder.stage("Поиск контактов")
        self.second = self.builder.stage("Встреча", after=(self.first,))
        self.find = self.builder.action(self.first, "Найти контакт", duration_days=3)
        self.optional = self.builder.action(self.first, "Позвонить", optional=True)
        self.meet = self.builder.action(self.second, "Организовать встречу")

    def stage_card(self, board: dict, name: str) -> dict:
        """Карточка этапа взаимодействия по названию."""
        return next(card for card in board["interaction_stages"] if card["stage"]["name"] == name)

    def action_card(self, board: dict, stage_name: str, action_name: str) -> dict:
        """Карточка действия этапа взаимодействия по названиям."""
        return next(card for card in self.stage_card(board, stage_name)["actions"] if card["name"] == action_name)

    def test_board_describes_process(self) -> None:
        """Шапка доски: процесс, его статус, workflow и взаимодействие."""
        process = self.start()

        board = board_service.build(process=process)

        # Проверяем шапку
        self.assertEqual(board["id"], process.pk)
        self.assertEqual(board["status"], process.status)
        self.assertEqual(board["workflow"], self.builder.workflow)
        self.assertEqual(board["interaction"], self.interaction)
        self.assertIsNone(board["completed_at"])

    def test_interaction_stages_come_in_display_order_with_statuses(self) -> None:
        """Этапы взаимодействия идут по порядку показа, у каждого — статус и время."""
        process = self.start()

        board = board_service.build(process=process)

        first, second = board["interaction_stages"]
        # Проверяем порядок, идентификаторы и статусы
        self.assertEqual([first["stage"]["name"], second["stage"]["name"]], ["Поиск контактов", "Встреча"])
        self.assertEqual(first["id"], self.stage_instance(process, self.first).pk)
        self.assertEqual(first["stage"]["id"], self.first.pk)
        self.assertEqual(first["status"], StageInstanceStatus.IN_PROGRESS)
        self.assertIsNotNone(first["started_at"])
        self.assertEqual(second["status"], StageInstanceStatus.PENDING)
        self.assertIsNone(second["started_at"])

    def test_action_card_describes_action_in_progress(self) -> None:
        """Карточка действия в работе: статус, даты, признаки и исходы, которые можно выбрать."""
        process = self.start()

        card = self.action_card(board_service.build(process=process), "Поиск контактов", "Найти контакт")

        instance = self.action_instance(process, self.find)
        # Проверяем описание действия
        self.assertEqual(card["id"], instance.pk)
        self.assertEqual(card["action"], {"id": self.find.pk, "name": "Найти контакт"})
        self.assertEqual(card["status"], IN_PROGRESS)
        self.assertFalse(card["is_optional"])
        self.assertFalse(card["starts_by_transition_only"])
        self.assertEqual(card["execution_no"], 1)
        # Проверяем даты и просрочку
        self.assertEqual(card["planned_end"], instance.planned_end)
        self.assertFalse(card["is_overdue"])
        # Проверяем, что результата и вложений нет, а исход «Выполнено» доступен
        self.assertIsNone(card["result"])
        self.assertEqual(card["attachments_count"], 0)
        outcome = self.find.action_outcomes.get(code="done")
        self.assertEqual(
            card["available_outcomes"],
            [
                {
                    "id": outcome.pk,
                    "code": "done",
                    "name": "Выполнено",
                    "comment_required": False,
                    "attachment_required": False,
                },
            ],
        )

    def test_optional_action_is_marked(self) -> None:
        """Необязательное действие помечено на карточке."""
        process = self.start()

        card = self.action_card(board_service.build(process=process), "Поиск контактов", "Позвонить")

        # Проверяем признак
        self.assertTrue(card["is_optional"])

    def test_pending_action_offers_no_outcomes(self) -> None:
        """Ожидающее действие исходов не предлагает."""
        process = self.start()

        card = self.action_card(board_service.build(process=process), "Встреча", "Организовать встречу")

        # Проверяем статус и отсутствие исходов
        self.assertEqual(card["status"], PENDING)
        self.assertEqual(card["available_outcomes"], [])

    def test_only_active_outcomes_are_offered(self) -> None:
        """Неактивный исход не предлагается."""
        self.builder.outcome(self.find, "obsolete", active=False)
        process = self.start()

        card = self.action_card(board_service.build(process=process), "Поиск контактов", "Найти контакт")

        # Проверяем список исходов
        self.assertEqual([item["code"] for item in card["available_outcomes"]], ["done"])

    def test_completed_action_shows_result_and_no_outcomes(self) -> None:
        """Выполненное действие показывает результат и исходов не предлагает."""
        process = self.start()
        self.complete(process, self.find, comment="Нашли")

        card = self.action_card(board_service.build(process=process), "Поиск контактов", "Найти контакт")

        # Проверяем статус, результат и отсутствие исходов
        self.assertEqual(card["status"], COMPLETED)
        self.assertEqual(card["result"]["outcome_name"], "Выполнено")
        self.assertEqual(card["result"]["comment"], "Нашли")
        self.assertEqual(card["result"]["created_by"], self.user)
        self.assertIsNotNone(card["result"]["created_at"])
        self.assertEqual(card["available_outcomes"], [])
        self.assertFalse(card["is_overdue"])

    def test_overdue_is_reported_only_for_action_in_progress(self) -> None:
        """Просрочено действие в работе, плановое окончание которого прошло."""
        process = self.start()
        ActionInstance.objects.filter(pk=self.action_instance(process, self.find).pk).update(
            planned_end=timezone.now() - timedelta(days=1),
        )

        card = self.action_card(board_service.build(process=process), "Поиск контактов", "Найти контакт")

        # Проверяем просрочку
        self.assertTrue(card["is_overdue"])

    def test_attachments_are_counted(self) -> None:
        """На карточке показано число вложений."""
        process = self.start()
        ActionAttachmentFactory.create_batch(size=2, action_instance=self.action_instance(process, self.find))

        card = self.action_card(board_service.build(process=process), "Поиск контактов", "Найти контакт")

        # Проверяем число вложений
        self.assertEqual(card["attachments_count"], 2)

    def test_card_shows_latest_execution_of_repeated_action(self) -> None:
        """Повторно запущенное действие показано последним исполнением, без результата."""
        again = self.builder.outcome(self.find, "again")
        self.builder.branch(again, self.find)
        process = self.start()
        self.complete(process, self.find, code="again")

        card = self.action_card(board_service.build(process=process), "Поиск контактов", "Найти контакт")

        # Проверяем номер исполнения, статус и отсутствие результата
        self.assertEqual(card["execution_no"], 2)
        self.assertEqual(card["status"], IN_PROGRESS)
        self.assertIsNone(card["result"])

    def test_conditional_action_reports_whether_it_was_triggered(self) -> None:
        """Действие «только по переходу» показывает, запущено ли оно."""
        fix = self.builder.action(self.first, "Исправить", trigger_only=True)
        self.builder.branch(self.builder.outcome(self.find, "needs_fix"), fix)
        process = self.start()

        before = self.action_card(board_service.build(process=process), "Поиск контактов", "Исправить")
        self.complete(process, self.find, code="needs_fix")
        after = self.action_card(board_service.build(process=process), "Поиск контактов", "Исправить")

        # Проверяем признаки до и после запуска
        self.assertTrue(before["starts_by_transition_only"])
        self.assertFalse(before["is_triggered"])
        self.assertTrue(after["is_triggered"])

    def test_return_options_are_predecessors_of_stage_in_progress(self) -> None:
        """Для этапа в работе предложены предшественники; для первого этапа и закрытых — пусто."""
        process = self.start()
        first_board = board_service.build(process=process)
        # Проверяем, что у первого этапа предшественников нет
        self.assertEqual(self.stage_card(first_board, "Поиск контактов")["return_options"], [])

        self.complete(process, self.find)
        board = board_service.build(process=process)

        # Проверяем варианты возврата для открытого этапа и пустоту для закрытого
        self.assertEqual(
            self.stage_card(board, "Встреча")["return_options"],
            [{"id": self.stage_instance(process, self.first).pk, "stage_name": "Поиск контактов"}],
        )
        self.assertEqual(self.stage_card(board, "Поиск контактов")["return_options"], [])


class BoardContextsTest(EngineTestCase):
    """Тесты доски для этапов направлений, программ и продуктов."""

    def setUp(self) -> None:
        """Подписание, после него этапы продукта и программы."""
        super().setUp()
        self.signing = self.builder.stage("Подписание")
        self.sign = self.builder.action(self.signing, "Подписать")
        self.product_stage = self.builder.stage("Продукт", after=(self.signing,), type=PRODUCT)
        self.transfer = self.builder.action(self.product_stage, "Передать лицензию")
        self.program_stage = self.builder.stage("Программа", after=(self.signing,), type=PROGRAM)
        self.update_program = self.builder.action(self.program_stage, "Актуализировать программу")
        self.program = InteractionProgramFactory(interaction=self.interaction)
        self.product = InteractionProductFactory(interaction=self.interaction, interaction_program=self.program)

    def test_groups_describe_contexts_with_titles_and_parent(self) -> None:
        """Для каждого продукта и программы есть группа: тип, контекст, название, родитель и этапы."""
        process = self.start()

        board = board_service.build(process=process)

        groups = {group["context_id"]: group for group in board["context_groups"]}
        product_group = groups[self.product.pk]
        program_group = groups[self.program.pk]
        # Проверяем группу продукта
        self.assertEqual(product_group["context_type"], PRODUCT)
        self.assertEqual(product_group["title"], self.product.it_product.name)
        self.assertEqual(product_group["parent_id"], self.program.pk)
        self.assertEqual([card["stage"]["name"] for card in product_group["stages"]], ["Продукт"])
        self.assertEqual(product_group["stages"][0]["status"], StageInstanceStatus.PENDING)
        # Проверяем группу программы
        self.assertEqual(program_group["context_type"], PROGRAM)
        self.assertEqual(program_group["title"], self.program.it_program.name)
        self.assertIsNone(program_group["parent_id"])

    def test_product_without_program_has_no_parent(self) -> None:
        """Продукт вне программы не имеет родителя."""
        lone = InteractionProductFactory(interaction=self.interaction)
        process = self.start()

        board = board_service.build(process=process)

        group = next(item for item in board["context_groups"] if item["context_id"] == lone.pk)
        # Проверяем родителя
        self.assertIsNone(group["parent_id"])

    def test_groups_are_ordered_by_type_then_title(self) -> None:
        """Группы идут по типу (направления, программы, продукты), затем по названию."""
        direction_stage = self.builder.stage("Направление", after=(self.signing,), type=DIRECTION)
        self.builder.action(direction_stage, "Актуализировать направление")
        direction = InteractionDirectionFactory(interaction=self.interaction)
        process = self.start()

        board = board_service.build(process=process)

        # Проверяем порядок типов
        self.assertEqual(
            [group["context_type"] for group in board["context_groups"]],
            [DIRECTION, PROGRAM, PRODUCT],
        )
        self.assertEqual(board["context_groups"][0]["context_id"], direction.pk)

    def test_deactivated_context_is_not_shown(self) -> None:
        """Деактивированный продукт на доске не показывается."""
        process = self.start()
        self.product.is_active = False
        self.product.save()

        board = board_service.build(process=process)

        # Проверяем, что группы продукта нет
        self.assertNotIn(self.product.pk, [group["context_id"] for group in board["context_groups"]])

    def test_product_stage_offers_signing_as_return_option(self) -> None:
        """Отмена этапа продукта возвращает на подписание — оно и предложено."""
        process = self.start()
        self.complete(process, self.sign)

        board = board_service.build(process=process)

        group = next(item for item in board["context_groups"] if item["context_id"] == self.product.pk)
        # Проверяем вариант возврата
        self.assertEqual(
            group["stages"][0]["return_options"],
            [{"id": self.stage_instance(process, self.signing).pk, "stage_name": "Подписание"}],
        )
        self.assertEqual(group["stages"][0]["actions"][0]["status"], IN_PROGRESS)

    def test_query_count_does_not_depend_on_number_of_contexts(self) -> None:
        """Число запросов доски не растёт с числом продуктов: нет N+1."""
        process = self.start()
        self.complete(process, self.sign)
        with CaptureQueriesContext(connection) as small:
            board_service.build(process=process)

        for _ in range(4):
            InteractionProductFactory(interaction=self.interaction, interaction_program=self.program)
        self.complete(process, self.update_program, context=self.program)
        with CaptureQueriesContext(connection) as large:
            board = board_service.build(process=process)

        # Проверяем, что продуктов стало больше, а запросов — столько же
        self.assertEqual(len([g for g in board["context_groups"] if g["context_type"] == PRODUCT]), 5)
        self.assertEqual(len(large), len(small))
