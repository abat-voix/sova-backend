from datetime import timedelta

from sova.catalog.tests.factories import B2CClientFactory
from sova.interactions.tests.factories import (
    InteractionDirectionFactory,
    InteractionFactory,
    InteractionProductFactory,
    InteractionProgramFactory,
    ResponsibleFactory,
)
from sova.processes.enum import RollbackMode, StageInstanceStatus, WorkflowInstanceStatus
from sova.processes.exceptions import InvalidStateError, RuleViolationError
from sova.processes.models import ActionInstance, ActionResult, ActionRollback, StageInstance, StageRollback
from sova.processes.services import workflow_engine_service as engine
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
from sova.workflows.enum import Audience
from sova.workflows.models import ActionOutcome
from sova.workflows.tests.builders import WorkflowBuilder


class StartTest(EngineTestCase):
    """Тесты запуска процесса: экземпляры этапов и действий создаются сразу, открывается только начало."""

    def test_start_creates_running_process(self) -> None:
        """Процесс идёт и запомнил workflow, взаимодействие и автора."""
        stage = self.builder.stage("Поиск контактов")
        self.builder.action(stage, "Найти контакт")

        process = self.start()

        # Проверяем поля процесса
        self.assertEqual(process.status, WorkflowInstanceStatus.RUNNING)
        self.assertEqual(process.workflow, self.builder.workflow)
        self.assertEqual(process.interaction, self.interaction)
        self.assertEqual(process.created_by, self.user)
        self.assertIsNone(process.completed_at)

    def test_start_opens_stages_without_incoming_transitions_only(self) -> None:
        """Открывается этап без входящих связей, остальные ждут."""
        first = self.builder.stage("Первый")
        second = self.builder.stage("Второй", after=(first,))
        self.builder.action(first, "А")
        self.builder.action(second, "Б")

        process = self.start()

        # Проверяем статусы этапов и момент открытия
        self.assertEqual(self.stage_status(process, first), StageInstanceStatus.IN_PROGRESS)
        self.assertIsNotNone(self.stage_instance(process, first).started_at)
        self.assertEqual(self.stage_status(process, second), StageInstanceStatus.PENDING)
        self.assertIsNone(self.stage_instance(process, second).started_at)

    def test_start_opens_every_root_stage(self) -> None:
        """Все этапы без входящих связей открываются сразу."""
        first = self.builder.stage("Первый")
        second = self.builder.stage("Второй")
        self.builder.action(first, "А")
        self.builder.action(second, "Б")

        process = self.start()

        # Проверяем, что оба корня открыты
        self.assertEqual(self.stage_status(process, first), StageInstanceStatus.IN_PROGRESS)
        self.assertEqual(self.stage_status(process, second), StageInstanceStatus.IN_PROGRESS)

    def test_start_creates_action_instances_with_name_snapshot(self) -> None:
        """Для каждого действия создаётся первое исполнение со слепком названия."""
        stage = self.builder.stage("Первый")
        action = self.builder.action(stage, "Найти контакт")

        process = self.start()

        instance = self.action_instance(process, action)
        # Проверяем номер исполнения и слепок названия
        self.assertEqual(instance.execution_no, 1)
        self.assertEqual(instance.action_name_snapshot, "Найти контакт")

    def test_start_makes_ready_actions_available_and_keeps_dependent_waiting(self) -> None:
        """Действие без зависимостей доступно сразу, зависимое ждёт."""
        stage = self.builder.stage("Первый")
        free = self.builder.action(stage, "Свободное")
        waiting = self.builder.action(stage, "Зависимое", after=(free,))

        process = self.start()

        # Проверяем статусы действий
        self.assertEqual(self.action_status(process, free), IN_PROGRESS)
        self.assertEqual(self.action_status(process, waiting), PENDING)

    def test_start_plans_dates_from_default_duration(self) -> None:
        """Плановое окончание — плановое начало плюс длительность действия."""
        stage = self.builder.stage("Первый")
        action = self.builder.action(stage, "С длительностью", duration_days=5)
        untimed = self.builder.action(stage, "Без длительности")

        process = self.start()

        timed = self.action_instance(process, action)
        # Проверяем даты действия с длительностью
        self.assertEqual(timed.actual_start, timed.planned_start)
        self.assertEqual(timed.planned_end - timed.planned_start, timedelta(days=5))
        # Проверяем, что без длительности действие планируется на сутки
        untimed_instance = self.action_instance(process, untimed)
        self.assertEqual(untimed_instance.planned_end - untimed_instance.planned_start, timedelta(days=1))

    def test_start_leaves_responsible_empty_with_manager(self) -> None:
        """Действия создаются в пуле КАМов взаимодействия, даже если КАМ один."""
        ResponsibleFactory(interaction=self.interaction)
        stage = self.builder.stage("Первый")
        action = self.builder.action(stage, "А")

        process = self.start()

        # Проверяем пустого ответственного
        self.assertIsNone(self.action_instance(process, action).responsible)

    def test_start_leaves_responsible_empty_without_manager(self) -> None:
        """Без назначенного менеджера ответственного у действия нет."""
        stage = self.builder.stage("Первый")
        action = self.builder.action(stage, "А")

        process = self.start()

        # Проверяем пустого ответственного
        self.assertIsNone(self.action_instance(process, action).responsible)

    def test_start_ignores_inactive_stages_and_actions(self) -> None:
        """Неактивные этапы и действия в процесс не попадают."""
        stage = self.builder.stage("Первый")
        active = self.builder.action(stage, "Активное")
        inactive = self.builder.action(stage, "Неактивное")
        inactive.is_active = False
        inactive.save()
        disabled_stage = self.builder.stage("Выключенный")
        disabled_stage.is_active = False
        disabled_stage.save()
        self.builder.action(disabled_stage, "В выключенном")

        process = self.start()

        # Проверяем, что созданы только активные экземпляры
        self.assertEqual(StageInstance.objects.filter(workflow_instance=process).count(), 1)
        self.assertEqual(ActionInstance.objects.filter(stage_instance__workflow_instance=process).count(), 1)
        self.assertEqual(self.action_instance(process, active).action, active)

    def test_start_creates_stage_instance_for_each_active_context(self) -> None:
        """Этап продукта создаётся для каждого активного продукта, неактивный пропускается."""
        first = self.builder.stage("Первый")
        product_stage = self.builder.stage("Продукт", after=(first,), type=PRODUCT)
        self.builder.action(first, "А")
        self.builder.action(product_stage, "Передать лицензию")
        products = InteractionProductFactory.create_batch(size=2, interaction=self.interaction)
        InteractionProductFactory(interaction=self.interaction, is_active=False)

        process = self.start()

        created = StageInstance.objects.filter(workflow_instance=process, stage=product_stage)
        # Проверяем контексты и статусы созданных этапов
        self.assertEqual({instance.context_id for instance in created}, {product.pk for product in products})
        self.assertEqual({instance.status for instance in created}, {StageInstanceStatus.PENDING})
        self.assertEqual({instance.context_type for instance in created}, {PRODUCT})

    def test_start_creates_stage_instances_for_programs_and_directions(self) -> None:
        """Этапы программ и направлений создаются по своим контекстам."""
        first = self.builder.stage("Первый")
        program_stage = self.builder.stage("Программа", after=(first,), type=PROGRAM)
        direction_stage = self.builder.stage("Направление", after=(first,), type=DIRECTION)
        self.builder.action(first, "А")
        self.builder.action(program_stage, "Актуализировать программу")
        self.builder.action(direction_stage, "Актуализировать направление")
        program = InteractionProgramFactory(interaction=self.interaction)
        direction = InteractionDirectionFactory(interaction=self.interaction)

        process = self.start()

        # Проверяем, что этапы созданы по своим контекстам
        self.assertEqual(self.stage_instance(process, program_stage, program).context_type, PROGRAM)
        self.assertEqual(self.stage_instance(process, direction_stage, direction).context_type, DIRECTION)

    def test_start_creates_no_instances_for_context_stage_without_contexts(self) -> None:
        """Этап продукта не создаёт экземпляров, если у взаимодействия нет продуктов."""
        first = self.builder.stage("Первый")
        product_stage = self.builder.stage("Продукт", after=(first,), type=PRODUCT)
        self.builder.action(first, "А")
        self.builder.action(product_stage, "Б")

        process = self.start()

        # Проверяем отсутствие экземпляров
        self.assertFalse(StageInstance.objects.filter(workflow_instance=process, stage=product_stage).exists())

    def test_start_rejects_inactive_workflow(self) -> None:
        """Неактивный workflow запустить нельзя."""
        stage = self.builder.stage("Первый")
        self.builder.action(stage, "А")
        self.builder.workflow.is_active = False
        self.builder.workflow.save()

        # Проверяем код ошибки
        with self.assertRaises(RuleViolationError) as raised:
            self.start()
        self.assertEqual(raised.exception.code, "workflow_inactive")

    def test_start_rejects_workflow_of_another_audience(self) -> None:
        """B2C-workflow нельзя запустить для взаимодействия с вузом."""
        builder = WorkflowBuilder(audience=Audience.B2C)
        stage = builder.stage("Первый")
        builder.action(stage, "А")

        # Проверяем код ошибки
        with self.assertRaises(RuleViolationError) as raised:
            engine.start(workflow=builder.workflow, interaction=self.interaction, started_by=self.user)
        self.assertEqual(raised.exception.code, "audience_mismatch")

    def test_start_accepts_b2c_workflow_for_b2c_client(self) -> None:
        """B2C-workflow запускается для взаимодействия с B2C-клиентом."""
        builder = WorkflowBuilder(audience=Audience.B2C)
        stage = builder.stage("Первый")
        builder.action(stage, "А")
        interaction = InteractionFactory(organization=None, b2c_client=B2CClientFactory())

        process = engine.start(workflow=builder.workflow, interaction=interaction, started_by=self.user)

        # Проверяем, что процесс запущен
        self.assertEqual(process.status, WorkflowInstanceStatus.RUNNING)

    def test_start_rejects_workflow_without_active_stages(self) -> None:
        """Пустой workflow запустить нельзя."""
        # Проверяем код ошибки
        with self.assertRaises(RuleViolationError) as raised:
            self.start()
        self.assertEqual(raised.exception.code, "empty_workflow")

    def test_start_rejects_second_process_of_same_workflow(self) -> None:
        """Тот же workflow для того же взаимодействия дважды не запускается."""
        stage = self.builder.stage("Первый")
        self.builder.action(stage, "А")
        self.start()

        # Проверяем код ошибки
        with self.assertRaises(InvalidStateError) as raised:
            self.start()
        self.assertEqual(raised.exception.code, "already_started")


class CompleteActionTest(EngineTestCase):
    """Тесты завершения действия: результат, проверки исхода и состояние действия."""

    def setUp(self) -> None:
        """Одноэтапный workflow с одним действием."""
        super().setUp()
        self.stage = self.builder.stage("Первый")
        self.action = self.builder.action(self.stage, "Найти контакт")

    def test_complete_records_result_and_finishes_action(self) -> None:
        """Завершение создаёт результат со слепком названия исхода и комментарием."""
        process = self.start()

        outcome = self.complete(process, self.action, comment="Нашли")

        instance = self.action_instance(process, self.action)
        result = ActionResult.objects.get(action_instance=instance)
        # Проверяем результат
        self.assertEqual(outcome.result, result)
        self.assertEqual(result.outcome_name_snapshot, "Выполнено")
        self.assertEqual(result.comment, "Нашли")
        self.assertEqual(result.created_by, self.user)
        # Проверяем состояние действия
        self.assertEqual(instance.status, COMPLETED)
        self.assertIsNotNone(instance.actual_end)
        self.assertEqual(outcome.action_instance, instance)

    def test_complete_assigns_completing_user_when_responsible_is_empty(self) -> None:
        """Пустой ответственный заменяется завершившим пользователем."""
        process = self.start()

        self.complete(process, self.action)

        # Проверяем ответственного
        self.assertEqual(self.action_instance(process, self.action).responsible, self.user)

    def test_complete_keeps_existing_responsible(self) -> None:
        """Назначенный ответственный не заменяется."""
        manager = ResponsibleFactory(interaction=self.interaction).manager
        process = self.start()
        instance = self.action_instance(process, self.action)
        instance.responsible = manager
        instance.save(update_fields=["responsible"])

        self.complete(process, self.action)

        # Проверяем, что ответственный прежний
        self.assertEqual(self.action_instance(process, self.action).responsible, manager)

    def test_complete_rejects_action_that_is_not_in_progress(self) -> None:
        """Ожидающее действие завершить нельзя."""
        waiting = self.builder.action(self.stage, "Зависимое", after=(self.action,))
        process = self.start()

        # Проверяем код ошибки
        with self.assertRaises(InvalidStateError) as raised:
            self.complete(process, waiting)
        self.assertEqual(raised.exception.code, "invalid_state")

    def test_complete_rejects_already_completed_action(self) -> None:
        """Повторное завершение того же исполнения отвергается."""
        self.builder.action(self.stage, "Ещё одно")
        process = self.start()
        instance = self.action_instance(process, self.action)
        outcome = ActionOutcome.objects.get(action=self.action, code="done")
        engine.complete_action(action_instance=instance, outcome=outcome, comment="", completed_by=self.user)

        # Проверяем код ошибки и то, что результат один
        with self.assertRaises(InvalidStateError):
            engine.complete_action(action_instance=instance, outcome=outcome, comment="", completed_by=self.user)
        self.assertEqual(ActionResult.objects.filter(action_instance=instance).count(), 1)

    def test_complete_rejects_outcome_of_another_action(self) -> None:
        """Исход другого действия не подходит."""
        other = self.builder.action(self.stage, "Другое")
        process = self.start()

        # Проверяем код ошибки
        with self.assertRaises(RuleViolationError) as raised:
            engine.complete_action(
                action_instance=self.action_instance(process, self.action),
                outcome=ActionOutcome.objects.get(action=other, code="done"),
                comment="",
                completed_by=self.user,
            )
        self.assertEqual(raised.exception.code, "outcome_mismatch")

    def test_complete_rejects_inactive_outcome(self) -> None:
        """Неактивный исход не подходит."""
        outcome = ActionOutcome.objects.get(action=self.action, code="done")
        outcome.is_active = False
        outcome.save()
        process = self.start()

        # Проверяем код ошибки
        with self.assertRaises(RuleViolationError) as raised:
            self.complete(process, self.action)
        self.assertEqual(raised.exception.code, "outcome_inactive")

    def test_complete_requires_comment_when_outcome_demands_it(self) -> None:
        """Исход с обязательным комментарием не принимает пустой и состоящий из пробелов."""
        self.builder.outcome(self.action, "agreed", is_comment_required=True)
        process = self.start()

        for comment in ("", "   "):
            with self.subTest(comment=comment):
                # Проверяем код ошибки
                with self.assertRaises(RuleViolationError) as raised:
                    self.complete(process, self.action, code="agreed", comment=comment)
                self.assertEqual(raised.exception.code, "is_comment_required")
        # Проверяем, что состояние не изменилось
        self.assertEqual(self.action_status(process, self.action), IN_PROGRESS)
        self.assertFalse(ActionResult.objects.exists())

    def test_complete_accepts_comment_when_outcome_demands_it(self) -> None:
        """Исход с обязательным комментарием принимает непустой."""
        self.builder.outcome(self.action, "agreed", is_comment_required=True)
        process = self.start()

        self.complete(process, self.action, code="agreed", comment="Согласовано")

        # Проверяем, что действие завершено
        self.assertEqual(self.action_status(process, self.action), COMPLETED)

    def test_complete_requires_attachment_when_outcome_demands_it(self) -> None:
        """Исход с обязательным вложением требует файл у этого исполнения."""
        self.builder.outcome(self.action, "signed", is_attachment_required=True)
        process = self.start()

        # Проверяем код ошибки без вложения
        with self.assertRaises(RuleViolationError) as raised:
            self.complete(process, self.action, code="signed")
        self.assertEqual(raised.exception.code, "is_attachment_required")

        ActionAttachmentFactory(action_instance=self.action_instance(process, self.action))
        self.complete(process, self.action, code="signed")

        # Проверяем, что с вложением действие завершено
        self.assertEqual(self.action_status(process, self.action), COMPLETED)


class StageLifecycleTest(EngineTestCase):
    """Тесты открытия и закрытия этапов: закрывают обязательные действия, опциональные остаются доступными."""

    def test_completing_last_mandatory_action_closes_stage_and_opens_next(self) -> None:
        """Последнее обязательное действие закрывает этап и открывает следующий."""
        first = self.builder.stage("Первый")
        second = self.builder.stage("Второй", after=(first,))
        action = self.builder.action(first, "А")
        next_action = self.builder.action(second, "Б")
        process = self.start()

        outcome = self.complete(process, action)

        closed = self.stage_instance(process, first)
        # Проверяем статусы и время
        self.assertEqual(closed.status, StageInstanceStatus.COMPLETED)
        self.assertIsNotNone(closed.completed_at)
        self.assertEqual(self.stage_status(process, second), StageInstanceStatus.IN_PROGRESS)
        self.assertEqual(self.action_status(process, next_action), IN_PROGRESS)
        # Проверяем описание изменений в ответе
        self.assertEqual(outcome.completed_stages, [closed])
        self.assertEqual(outcome.opened_stages, [self.stage_instance(process, second)])
        self.assertIn(self.action_instance(process, next_action), outcome.activated_actions)

    def test_stage_stays_open_until_all_mandatory_actions_are_done(self) -> None:
        """Пока не выполнены все обязательные действия, этап не закрывается."""
        first = self.builder.stage("Первый")
        second = self.builder.stage("Второй", after=(first,))
        a = self.builder.action(first, "А")
        b = self.builder.action(first, "Б")
        self.builder.action(second, "В")
        process = self.start()

        self.complete(process, a)

        # Проверяем, что этап открыт, а следующий ждёт
        self.assertEqual(self.stage_status(process, first), StageInstanceStatus.IN_PROGRESS)
        self.assertEqual(self.stage_status(process, second), StageInstanceStatus.PENDING)

        self.complete(process, b)

        # Проверяем, что после последнего действия этап закрыт
        self.assertEqual(self.stage_status(process, first), StageInstanceStatus.COMPLETED)
        self.assertEqual(self.stage_status(process, second), StageInstanceStatus.IN_PROGRESS)

    def test_independent_actions_start_together(self) -> None:
        """Независимые действия доступны одновременно."""
        stage = self.builder.stage("Первый")
        banana = self.builder.action(stage, "Найти банан")
        orange = self.builder.action(stage, "Найти апельсин")

        process = self.start()

        # Проверяем, что оба в работе
        self.assertEqual(self.action_status(process, banana), IN_PROGRESS)
        self.assertEqual(self.action_status(process, orange), IN_PROGRESS)

    def test_dependent_action_starts_after_its_prerequisite(self) -> None:
        """Зависимое действие стартует после выполнения предусловия."""
        stage = self.builder.stage("Первый")
        products = self.builder.action(stage, "Найти продукты")
        dinner = self.builder.action(stage, "Приготовить обед", after=(products,))
        process = self.start()

        outcome = self.complete(process, products)

        # Проверяем запуск и даты
        instance = self.action_instance(process, dinner)
        self.assertEqual(instance.status, IN_PROGRESS)
        self.assertIsNotNone(instance.actual_start)
        self.assertEqual(outcome.activated_actions, [instance])

    def test_diamond_dependency_waits_for_both_branches(self) -> None:
        """Действие с двумя предусловиями стартует после обоих."""
        stage = self.builder.stage("Первый")
        a = self.builder.action(stage, "А")
        b = self.builder.action(stage, "Б", after=(a,))
        c = self.builder.action(stage, "В", after=(a,))
        d = self.builder.action(stage, "Г", after=(b, c))
        process = self.start()

        self.complete(process, a)
        self.complete(process, b)
        # Проверяем, что после одной ветки Г ждёт
        self.assertEqual(self.action_status(process, d), PENDING)

        self.complete(process, c)

        # Проверяем, что после обеих веток Г стартует
        self.assertEqual(self.action_status(process, d), IN_PROGRESS)

    def test_optional_action_does_not_block_closure_and_stays_available(self) -> None:
        """Необязательное действие не мешает закрытию и остаётся доступным после него."""
        first = self.builder.stage("Первый")
        second = self.builder.stage("Второй", after=(first,))
        mandatory = self.builder.action(first, "Обязательное")
        optional = self.builder.action(first, "Необязательное", optional=True)
        self.builder.action(second, "Следующее")
        process = self.start()

        self.complete(process, mandatory)

        # Проверяем, что этап закрыт, следующий открыт, а необязательное доступно
        self.assertEqual(self.stage_status(process, first), StageInstanceStatus.COMPLETED)
        self.assertEqual(self.stage_status(process, second), StageInstanceStatus.IN_PROGRESS)
        self.assertEqual(self.action_status(process, optional), IN_PROGRESS)

        self.complete(process, optional)

        # Проверяем, что необязательное завершается после закрытия этапа и этап остаётся закрытым
        self.assertEqual(self.action_status(process, optional), COMPLETED)
        self.assertEqual(self.stage_status(process, first), StageInstanceStatus.COMPLETED)

    def test_optional_action_waiting_for_optional_starts_after_stage_closed(self) -> None:
        """Ждущее необязательное действие стартует и в уже закрытом этапе."""
        stage = self.builder.stage("Первый")
        mandatory = self.builder.action(stage, "Обязательное")
        first_optional = self.builder.action(stage, "Первое необязательное", optional=True)
        second_optional = self.builder.action(stage, "Второе необязательное", optional=True, after=(first_optional,))
        process = self.start()
        self.complete(process, mandatory)

        self.complete(process, first_optional)

        # Проверяем, что второе стартовало при закрытом этапе
        self.assertEqual(self.stage_status(process, stage), StageInstanceStatus.COMPLETED)
        self.assertEqual(self.action_status(process, second_optional), IN_PROGRESS)

    def test_stage_with_only_optional_actions_closes_on_opening(self) -> None:
        """Этап из одних необязательных действий закрывается сразу при открытии."""
        first = self.builder.stage("Первый")
        middle = self.builder.stage("Корректировка", after=(first,))
        last = self.builder.stage("Подписание", after=(middle,))
        start_action = self.builder.action(first, "Обмен документами")
        optional = self.builder.action(middle, "Скорректировать документы", optional=True)
        self.builder.action(last, "Подписать")
        process = self.start()

        outcome = self.complete(process, start_action)

        # Проверяем, что средний этап пройден, а последний открыт
        self.assertEqual(self.stage_status(process, middle), StageInstanceStatus.COMPLETED)
        self.assertEqual(self.stage_status(process, last), StageInstanceStatus.IN_PROGRESS)
        self.assertIn(self.stage_instance(process, middle), outcome.completed_stages)
        # Проверяем, что необязательное действие осталось доступным
        self.assertEqual(self.action_status(process, optional), IN_PROGRESS)

    def test_stage_without_actions_closes_on_opening(self) -> None:
        """Этап без действий закрывается сразу при открытии."""
        first = self.builder.stage("Первый")
        empty = self.builder.stage("Пустой", after=(first,))
        last = self.builder.stage("Последний", after=(empty,))
        action = self.builder.action(first, "А")
        self.builder.action(last, "Б")
        process = self.start()

        self.complete(process, action)

        # Проверяем, что пустой этап пройден и открыт последний
        self.assertEqual(self.stage_status(process, empty), StageInstanceStatus.COMPLETED)
        self.assertEqual(self.stage_status(process, last), StageInstanceStatus.IN_PROGRESS)

    def test_stage_with_several_predecessors_waits_for_all(self) -> None:
        """Этап с несколькими входящими связями открывается, когда закрыты все источники."""
        left = self.builder.stage("Левый")
        right = self.builder.stage("Правый")
        joint = self.builder.stage("Общий", after=(left, right))
        left_action = self.builder.action(left, "Л")
        right_action = self.builder.action(right, "П")
        self.builder.action(joint, "О")
        process = self.start()

        self.complete(process, left_action)
        # Проверяем, что после одного источника этап ждёт
        self.assertEqual(self.stage_status(process, joint), StageInstanceStatus.PENDING)

        self.complete(process, right_action)

        # Проверяем, что после обоих источников этап открыт
        self.assertEqual(self.stage_status(process, joint), StageInstanceStatus.IN_PROGRESS)

    def test_process_completes_when_all_stages_are_completed(self) -> None:
        """Процесс завершается, когда закрыты все этапы, даже если необязательные действия остались."""
        first = self.builder.stage("Первый")
        second = self.builder.stage("Второй", after=(first,))
        a = self.builder.action(first, "А")
        b = self.builder.action(second, "Б")
        self.builder.action(second, "Необязательное", optional=True)
        process = self.start()

        middle = self.complete(process, a)
        # Проверяем, что после первого этапа процесс идёт
        self.assertFalse(middle.is_workflow_completed)

        last = self.complete(process, b)

        process.refresh_from_db()
        # Проверяем завершение процесса
        self.assertTrue(last.is_workflow_completed)
        self.assertEqual(process.status, WorkflowInstanceStatus.COMPLETED)
        self.assertIsNotNone(process.completed_at)


class ConditionalActionTest(EngineTestCase):
    """Тесты ветвления по исходам внутри этапа: переходы запускают действия и повторы."""

    def setUp(self) -> None:
        """Этап с проверкой документов и исправлением, которое запускается только переходом."""
        super().setUp()
        self.stage = self.builder.stage("Обмен документами")
        self.check = self.builder.action(self.stage, "Проверить документы")
        self.fix = self.builder.action(self.stage, "Исправить документы", trigger_only=True)
        self.needs_fix = self.builder.outcome(self.check, "needs_fix")
        self.builder.branch(self.needs_fix, self.fix)

    def test_untriggered_action_is_pending_and_does_not_block_closure(self) -> None:
        """Не запущенное переходом обязательное действие ждёт и не мешает закрыть этап."""
        process = self.start()
        # Проверяем, что действие не стартовало вместе с этапом
        self.assertEqual(self.action_status(process, self.fix), PENDING)

        self.complete(process, self.check)

        # Проверяем, что этап закрыт, а действие осталось ждать
        self.assertEqual(self.stage_status(process, self.stage), StageInstanceStatus.COMPLETED)
        self.assertEqual(self.action_status(process, self.fix), PENDING)

    def test_outcome_transition_starts_the_action_and_it_blocks_closure(self) -> None:
        """Переход по исходу запускает действие, и запущенное обязательное блокирует закрытие."""
        process = self.start()

        outcome = self.complete(process, self.check, code="needs_fix")

        # Проверяем запуск и незакрытый этап
        self.assertEqual(self.action_status(process, self.fix), IN_PROGRESS)
        self.assertEqual(self.stage_status(process, self.stage), StageInstanceStatus.IN_PROGRESS)
        self.assertIn(self.action_instance(process, self.fix), outcome.activated_actions)

        self.complete(process, self.fix)

        # Проверяем, что после исправления этап закрыт
        self.assertEqual(self.stage_status(process, self.stage), StageInstanceStatus.COMPLETED)

    def test_triggered_action_waits_for_its_dependencies(self) -> None:
        """Запущенное переходом действие ждёт ещё и свои зависимости."""
        prepare = self.builder.action(self.stage, "Подготовить бланки")
        dependent = self.builder.action(self.stage, "Исправить с бланками", trigger_only=True, after=(prepare,))
        self.builder.branch(self.builder.outcome(self.check, "needs_forms"), dependent)
        process = self.start()

        self.complete(process, self.check, code="needs_forms")
        # Проверяем, что оно запущено, но ждёт предусловие
        instance = self.action_instance(process, dependent)
        self.assertEqual(instance.status, PENDING)
        self.assertIsNotNone(instance.triggered_at)

        self.complete(process, prepare)

        # Проверяем, что после предусловия оно стартовало
        self.assertEqual(self.action_status(process, dependent), IN_PROGRESS)

    def test_transition_to_completed_action_starts_new_execution(self) -> None:
        """Переход на уже выполненное действие создаёт новое исполнение, старый результат остаётся."""
        again = self.builder.outcome(self.check, "again")
        self.builder.branch(again, self.check)
        process = self.start()

        self.complete(process, self.check, code="again")

        executions = ActionInstance.objects.filter(
            stage_instance__workflow_instance=process,
            action=self.check,
        ).order_by("execution_no")
        # Проверяем два исполнения: старое завершено с результатом, новое в работе
        self.assertEqual([item.execution_no for item in executions], [1, 2])
        self.assertEqual(executions[0].status, COMPLETED)
        self.assertTrue(ActionResult.objects.filter(action_instance=executions[0]).exists())
        self.assertEqual(executions[1].status, IN_PROGRESS)
        # Проверяем, что старое исполнение за выполнившим, а новое — в пуле
        self.assertEqual(executions[0].responsible, self.user)
        self.assertIsNone(executions[1].responsible)
        # Проверяем, что этап остался открытым
        self.assertEqual(self.stage_status(process, self.stage), StageInstanceStatus.IN_PROGRESS)

    def test_transition_to_running_action_changes_nothing(self) -> None:
        """Переход на действие, которое уже в работе, ничего не меняет."""
        other = self.builder.action(self.stage, "Параллельное")
        self.builder.branch(self.builder.outcome(self.check, "to_other"), other)
        process = self.start()
        before = self.action_instance(process, other)

        self.complete(process, self.check, code="to_other")

        after = self.action_instance(process, other)
        # Проверяем, что исполнение то же и новых нет
        self.assertEqual(after.pk, before.pk)
        self.assertEqual(ActionInstance.objects.filter(action=other).count(), 1)

    def test_inactive_transition_is_ignored(self) -> None:
        """Неактивный переход не срабатывает."""
        dormant = self.builder.outcome(self.check, "dormant")
        self.builder.branch(dormant, self.fix, is_active=False)
        process = self.start()

        self.complete(process, self.check, code="dormant")

        # Проверяем, что действие не запущено и этап закрыт
        self.assertEqual(self.action_status(process, self.fix), PENDING)
        self.assertEqual(self.stage_status(process, self.stage), StageInstanceStatus.COMPLETED)


class ContextStagesTest(EngineTestCase):
    """Тесты этапов программ и продуктов: открываются после подписания и идут независимо."""

    def setUp(self) -> None:
        """Этап взаимодействия, за ним этап продукта из двух зависимых действий и этап программы."""
        super().setUp()
        self.signing = self.builder.stage("Подписание")
        self.sign = self.builder.action(self.signing, "Подписать")
        self.product_stage = self.builder.stage("Продукт", after=(self.signing,), type=PRODUCT)
        self.transfer = self.builder.action(self.product_stage, "Передать лицензию")
        self.rollout = self.builder.action(self.product_stage, "Внедрить", after=(self.transfer,))
        self.program_stage = self.builder.stage("Программа", after=(self.signing,), type=PROGRAM)
        self.update_program = self.builder.action(self.program_stage, "Актуализировать программу")
        self.first_product, self.second_product = InteractionProductFactory.create_batch(
            size=2,
            interaction=self.interaction,
        )
        self.program = InteractionProgramFactory(interaction=self.interaction)

    def test_all_products_and_programs_open_together_after_signing(self) -> None:
        """После закрытия подписания все продукты и программы открываются одновременно."""
        process = self.start()
        # Проверяем, что до подписания они ждут
        self.assertEqual(
            self.stage_status(process, self.product_stage, self.first_product),
            StageInstanceStatus.PENDING,
        )

        self.complete(process, self.sign)

        # Проверяем, что после подписания все открыты, а их первые действия в работе
        for context, stage, action in (
            (self.first_product, self.product_stage, self.transfer),
            (self.second_product, self.product_stage, self.transfer),
            (self.program, self.program_stage, self.update_program),
        ):
            with self.subTest(context=context):
                self.assertEqual(self.stage_status(process, stage, context), StageInstanceStatus.IN_PROGRESS)
                self.assertEqual(self.action_status(process, action, context), IN_PROGRESS)
        # Проверяем, что зависимое действие каждого продукта ждёт
        self.assertEqual(self.action_status(process, self.rollout, self.first_product), PENDING)

    def test_products_progress_independently(self) -> None:
        """Действие одного продукта не влияет на другой."""
        process = self.start()
        self.complete(process, self.sign)

        self.complete(process, self.transfer, context=self.first_product)

        # Проверяем, что дальше пошёл только первый продукт
        self.assertEqual(self.action_status(process, self.rollout, self.first_product), IN_PROGRESS)
        self.assertEqual(self.action_status(process, self.rollout, self.second_product), PENDING)
        self.assertEqual(self.action_status(process, self.transfer, self.second_product), IN_PROGRESS)

    def test_process_completes_only_after_every_context_is_done(self) -> None:
        """Процесс завершается, когда закрыты этапы всех продуктов и программ."""
        process = self.start()
        self.complete(process, self.sign)
        self.complete(process, self.update_program, context=self.program)
        for product in (self.first_product, self.second_product):
            self.complete(process, self.transfer, context=product)

        partial = self.complete(process, self.rollout, context=self.first_product)
        # Проверяем, что пока не все продукты готовы, процесс идёт
        self.assertFalse(partial.is_workflow_completed)

        final = self.complete(process, self.rollout, context=self.second_product)

        # Проверяем завершение процесса
        self.assertTrue(final.is_workflow_completed)

    def test_next_stage_of_same_context_opens_per_context(self) -> None:
        """Следующий этап продукта открывается только для того продукта, у которого закрыт предыдущий."""
        acceptance = self.builder.stage("Приёмка", after=(self.product_stage,), type=PRODUCT)
        accept = self.builder.action(acceptance, "Принять")
        process = self.start()
        self.complete(process, self.sign)

        self.complete(process, self.transfer, context=self.first_product)
        self.complete(process, self.rollout, context=self.first_product)

        # Проверяем, что приёмка открыта только у первого продукта
        self.assertEqual(self.stage_status(process, acceptance, self.first_product), StageInstanceStatus.IN_PROGRESS)
        self.assertEqual(self.action_status(process, accept, self.first_product), IN_PROGRESS)
        self.assertEqual(self.stage_status(process, acceptance, self.second_product), StageInstanceStatus.PENDING)

    def test_product_added_before_stage_opens_gets_its_stage(self) -> None:
        """Продукт, добавленный до открытия этапа, получает свой этап при следующем шаге процесса."""
        process = self.start()
        late_product = InteractionProductFactory(interaction=self.interaction)

        self.complete(process, self.sign)

        # Проверяем, что для позднего продукта этап создан и открыт
        self.assertEqual(self.stage_status(process, self.product_stage, late_product), StageInstanceStatus.IN_PROGRESS)
        self.assertEqual(self.action_status(process, self.transfer, late_product), IN_PROGRESS)

    def test_deactivated_context_is_ignored_when_opening_and_completing(self) -> None:
        """Деактивированный продукт этап не открывает и не мешает завершению процесса."""
        process = self.start()
        self.second_product.is_active = False
        self.second_product.save()

        self.complete(process, self.sign)

        # Проверяем, что этап деактивированного продукта остался ждать, а активного открыт
        self.assertEqual(
            self.stage_status(process, self.product_stage, self.second_product),
            StageInstanceStatus.PENDING,
        )
        self.assertEqual(
            self.stage_status(process, self.product_stage, self.first_product),
            StageInstanceStatus.IN_PROGRESS,
        )

        self.complete(process, self.update_program, context=self.program)
        self.complete(process, self.transfer, context=self.first_product)
        final = self.complete(process, self.rollout, context=self.first_product)

        # Проверяем, что процесс завершился, не дожидаясь деактивированного продукта
        self.assertTrue(final.is_workflow_completed)

    def test_interaction_stage_after_products_and_programs_waits_for_all_of_them(self) -> None:
        """Этап взаимодействия после этапов продукта и программы ждёт закрытия всех их активных экземпляров."""
        addendum = self.builder.stage("Допсоглашение", after=(self.product_stage, self.program_stage))
        sign_addendum = self.builder.action(addendum, "Подписать допсоглашение")
        process = self.start()
        self.complete(process, self.sign)
        self.complete(process, self.update_program, context=self.program)
        self.complete(process, self.transfer, context=self.first_product)
        self.complete(process, self.rollout, context=self.first_product)

        # Проверяем, что этап ждёт: второй продукт ещё не закрыт
        self.assertEqual(self.stage_status(process, addendum), StageInstanceStatus.PENDING)

        self.complete(process, self.transfer, context=self.second_product)
        self.complete(process, self.rollout, context=self.second_product)

        # Проверяем, что после закрытия всех продуктов и программ этап открылся
        self.assertEqual(self.stage_status(process, addendum), StageInstanceStatus.IN_PROGRESS)
        self.assertEqual(self.action_status(process, sign_addendum), IN_PROGRESS)


class CancelStageTest(EngineTestCase):
    """Тесты отката: отмена этапа возвращает процесс на предыдущий, сбрасывая действия."""

    def setUp(self) -> None:
        """Цепочка из трёх этапов; во втором две зависимые обязательные действия."""
        super().setUp()
        self.first = self.builder.stage("Первый")
        self.second = self.builder.stage("Второй", after=(self.first,))
        self.third = self.builder.stage("Третий", after=(self.second,))
        self.a1 = self.builder.action(self.first, "А1")
        self.a2 = self.builder.action(self.second, "А2")
        self.a3 = self.builder.action(self.second, "А3", after=(self.a2,))
        self.a4 = self.builder.action(self.third, "А4")

    def reach_third_stage(self):
        """Доводит процесс до открытого третьего этапа."""
        process = self.start()
        for action in (self.a1, self.a2, self.a3):
            self.complete(process, action)
        return process

    def test_cancel_restarts_previous_stage_in_restart_mode(self) -> None:
        """Режим «заново»: отменённый этап ждёт, предыдущий открыт, его действия выполняются заново."""
        process = self.reach_third_stage()

        outcome = self.cancel(process, self.third, mode=RollbackMode.RESTART)

        # Проверяем статусы этапов
        self.assertEqual(self.stage_status(process, self.third), StageInstanceStatus.PENDING)
        self.assertEqual(self.stage_status(process, self.second), StageInstanceStatus.IN_PROGRESS)
        self.assertIsNone(self.stage_instance(process, self.second).completed_at)
        # Проверяем, что действия предыдущего этапа получили новое исполнение
        self.assertEqual(self.action_instance(process, self.a2).execution_no, 2)
        self.assertEqual(self.action_status(process, self.a2), IN_PROGRESS)
        self.assertEqual(self.action_instance(process, self.a3).execution_no, 2)
        self.assertEqual(self.action_status(process, self.a3), PENDING)
        # Проверяем, что новые исполнения в пуле
        self.assertIsNone(self.action_instance(process, self.a2).responsible)
        # Проверяем, что старые результаты остались
        self.assertEqual(ActionResult.objects.filter(action_instance__action__in=(self.a2, self.a3)).count(), 2)
        # Проверяем описание отката
        self.assertEqual(outcome.returned_stage, self.stage_instance(process, self.second))

    def test_cancel_reopens_only_last_mandatory_action_in_last_only_mode(self) -> None:
        """Режим «только последнее»: заново открывается только последнее обязательное действие."""
        process = self.reach_third_stage()

        self.cancel(process, self.third, mode=RollbackMode.LAST_ONLY)

        # Проверяем, что А3 открыто заново, а А2 осталось выполненным
        self.assertEqual(self.stage_status(process, self.second), StageInstanceStatus.IN_PROGRESS)
        self.assertEqual(self.action_instance(process, self.a3).execution_no, 2)
        self.assertEqual(self.action_status(process, self.a3), IN_PROGRESS)
        self.assertEqual(self.action_instance(process, self.a2).execution_no, 1)
        self.assertEqual(self.action_status(process, self.a2), COMPLETED)

    def test_last_mandatory_action_is_chosen_by_completion_time_not_order(self) -> None:
        """«Последнее» — выполненное позже всех, а не стоящее последним в списке."""
        independent = self.builder.action(self.second, "А5")
        process = self.start()
        self.complete(process, self.a1)
        self.complete(process, self.a2)
        self.complete(process, independent)
        self.complete(process, self.a3)

        self.cancel(process, self.third, mode=RollbackMode.LAST_ONLY)

        # Проверяем, что открыто именно А3, выполненное последним
        self.assertEqual(self.action_status(process, self.a3), IN_PROGRESS)
        self.assertEqual(self.action_status(process, independent), COMPLETED)

    def test_last_only_ignores_optional_actions_done_after_closure(self) -> None:
        """Необязательное действие, выполненное после закрытия этапа, «последним» не считается."""
        optional = self.builder.action(self.second, "Необязательное", optional=True)
        process = self.reach_third_stage()
        self.complete(process, optional)

        self.cancel(process, self.third, mode=RollbackMode.LAST_ONLY)

        # Проверяем, что открыто обязательное, а необязательное осталось выполненным
        self.assertEqual(self.action_status(process, self.a3), IN_PROGRESS)
        self.assertEqual(self.action_status(process, optional), COMPLETED)

    def test_last_only_fails_when_previous_stage_has_no_mandatory_actions(self) -> None:
        """Нельзя вернуться «только на последнее» в этап без обязательных действий."""
        optional_stage = self.builder.stage("Необязательный", after=(self.first,))
        self.builder.action(optional_stage, "Необязательное", optional=True)
        target = self.builder.stage("Целевой", after=(optional_stage,))
        self.builder.action(target, "Целевое")
        process = self.start()
        self.complete(process, self.a1)

        # Проверяем код ошибки
        with self.assertRaises(RuleViolationError) as raised:
            self.cancel(process, target, mode=RollbackMode.LAST_ONLY)
        self.assertEqual(raised.exception.code, "no_mandatory_action")

    def test_cancel_writes_journal_record(self) -> None:
        """Откат пишется в журнал: причина, режим, этапы и автор."""
        process = self.reach_third_stage()

        outcome = self.cancel(process, self.third, mode=RollbackMode.LAST_ONLY, reason="Клиент передумал")

        record = StageRollback.objects.get()
        # Проверяем запись журнала
        self.assertEqual(outcome.rollback, record)
        self.assertEqual(record.workflow_instance, process)
        self.assertEqual(record.reason, "Клиент передумал")
        self.assertEqual(record.mode, RollbackMode.LAST_ONLY)
        self.assertEqual(record.from_stage_instance, self.stage_instance(process, self.third))
        self.assertEqual(record.to_stage_instance, self.stage_instance(process, self.second))
        self.assertEqual(record.created_by, self.user)

    def test_cancel_requires_reason(self) -> None:
        """Причина обязательна: пустая и состоящая из пробелов отвергаются, состояние не меняется."""
        process = self.reach_third_stage()

        for reason in ("", "   "):
            with self.subTest(reason=reason):
                # Проверяем код ошибки
                with self.assertRaises(RuleViolationError) as raised:
                    self.cancel(process, self.third, reason=reason)
                self.assertEqual(raised.exception.code, "reason_required")
        # Проверяем, что откат не выполнен
        self.assertEqual(self.stage_status(process, self.third), StageInstanceStatus.IN_PROGRESS)
        self.assertFalse(StageRollback.objects.exists())

    def test_cancel_rejects_stage_that_is_not_in_progress(self) -> None:
        """Отменить можно только этап в работе: ожидающий и завершённый отвергаются."""
        process = self.reach_third_stage()

        # Проверяем закрытый этап
        with self.assertRaises(InvalidStateError):
            self.cancel(process, self.second)
        self.cancel(process, self.third)
        # Проверяем ожидающий этап
        with self.assertRaises(InvalidStateError):
            self.cancel(process, self.third)

    def test_cancel_rejects_stage_without_predecessor(self) -> None:
        """У первого этапа предшественника нет — откатывать некуда."""
        process = self.start()

        # Проверяем код ошибки
        with self.assertRaises(RuleViolationError) as raised:
            self.cancel(process, self.first)
        self.assertEqual(raised.exception.code, "no_predecessor")

    def test_cancel_resets_unfinished_actions_in_place(self) -> None:
        """Незавершённое действие отменённого этапа сбрасывается на месте, без нового исполнения."""
        process = self.reach_third_stage()
        before = self.action_instance(process, self.a4)
        self.assertEqual(before.status, IN_PROGRESS)

        self.cancel(process, self.third)

        after = self.action_instance(process, self.a4)
        # Проверяем, что та же запись ожидает и без дат
        self.assertEqual(after.pk, before.pk)
        self.assertEqual(after.execution_no, 1)
        self.assertEqual(after.status, PENDING)
        self.assertIsNone(after.actual_start)
        # План действие получает заново: откат обнулил прежний, планировщик проставил новый
        self.assertIsNotNone(after.planned_start)
        self.assertEqual(ActionInstance.objects.filter(action=self.a4).count(), 1)

    def test_cancel_keeps_history_of_completed_actions_of_cancelled_stage(self) -> None:
        """Выполненное действие отменённого этапа получает новое исполнение, старый результат остаётся."""
        extra = self.builder.action(self.third, "А6")
        process = self.reach_third_stage()
        self.complete(process, self.a4)
        self.assertEqual(self.stage_status(process, self.third), StageInstanceStatus.IN_PROGRESS)
        self.assertEqual(self.action_status(process, extra), IN_PROGRESS)

        self.cancel(process, self.third)

        # Проверяем историю выполненного действия
        executions = ActionInstance.objects.filter(action=self.a4).order_by("execution_no")
        self.assertEqual([item.status for item in executions], [COMPLETED, PENDING])
        self.assertTrue(ActionResult.objects.filter(action_instance=executions[0]).exists())

    def test_cancel_makes_triggered_action_untriggered_again(self) -> None:
        """Запуск переходом сбрасывается вместе с этапом."""
        fix = self.builder.action(self.third, "Исправить", trigger_only=True)
        self.builder.branch(self.builder.outcome(self.a4, "needs_fix"), fix)
        process = self.reach_third_stage()
        self.complete(process, self.a4, code="needs_fix")
        self.assertEqual(self.action_status(process, fix), IN_PROGRESS)

        self.cancel(process, self.third)

        instance = self.action_instance(process, fix)
        # Проверяем, что действие снова не запущено
        self.assertEqual(instance.status, PENDING)
        self.assertIsNone(instance.triggered_at)

    def test_cancel_requires_choice_when_stage_has_several_predecessors(self) -> None:
        """Если предшественников несколько, нужно выбрать этап возврата."""
        left = self.builder.stage("Левый")
        right = self.builder.stage("Правый")
        joint = self.builder.stage("Общий", after=(left, right))
        left_action = self.builder.action(left, "Л")
        right_action = self.builder.action(right, "П")
        self.builder.action(joint, "О")
        process = self.start()
        self.complete(process, left_action)
        self.complete(process, right_action)

        # Проверяем код ошибки без выбора
        with self.assertRaises(RuleViolationError) as raised:
            self.cancel(process, joint)
        self.assertEqual(raised.exception.code, "return_to_required")

        outcome = self.cancel(process, joint, return_to=self.stage_instance(process, left))

        # Проверяем, что процесс вернулся на выбранный этап, а второй остался закрытым
        self.assertEqual(outcome.returned_stage, self.stage_instance(process, left))
        self.assertEqual(self.stage_status(process, left), StageInstanceStatus.IN_PROGRESS)
        self.assertEqual(self.stage_status(process, right), StageInstanceStatus.COMPLETED)

    def test_cancel_rejects_return_to_that_is_not_a_predecessor(self) -> None:
        """Этап возврата обязан быть предшественником отменяемого."""
        process = self.reach_third_stage()

        # Проверяем код ошибки
        with self.assertRaises(RuleViolationError) as raised:
            self.cancel(process, self.third, return_to=self.stage_instance(process, self.first))
        self.assertEqual(raised.exception.code, "invalid_return_to")

    def test_cancel_resets_stages_downstream_of_returned_stage_only(self) -> None:
        """Сбрасываются этапы после этапа возврата; независимая ветка не затрагивается."""
        side = self.builder.stage("Боковой")
        side_action = self.builder.action(side, "Б")
        process = self.reach_third_stage()
        self.complete(process, side_action)

        self.cancel(process, self.third)

        # Проверяем, что независимая ветка осталась завершённой
        self.assertEqual(self.stage_status(process, side), StageInstanceStatus.COMPLETED)

    def test_cancelling_product_stage_returns_to_signing_and_resets_all_contexts(self) -> None:
        """Отмена этапа продукта возвращает на этап взаимодействия и сбрасывает все продукты и программы."""
        signing = self.builder.stage("Подписание", after=(self.third,))
        sign = self.builder.action(signing, "Подписать")
        product_stage = self.builder.stage("Продукт", after=(signing,), type=PRODUCT)
        transfer = self.builder.action(product_stage, "Передать")
        rollout = self.builder.action(product_stage, "Внедрить", after=(transfer,))
        program_stage = self.builder.stage("Программа", after=(signing,), type=PROGRAM)
        update = self.builder.action(program_stage, "Актуализировать")
        first_product, second_product = InteractionProductFactory.create_batch(size=2, interaction=self.interaction)
        program = InteractionProgramFactory(interaction=self.interaction)
        process = self.reach_third_stage()
        self.complete(process, self.a4)
        self.complete(process, sign)
        self.complete(process, transfer, context=second_product)
        self.complete(process, update, context=program)

        outcome = self.cancel(process, product_stage, context=first_product, mode=RollbackMode.LAST_ONLY)

        # Проверяем возврат на подписание с открытым последним действием
        self.assertEqual(outcome.returned_stage, self.stage_instance(process, signing))
        self.assertEqual(self.stage_status(process, signing), StageInstanceStatus.IN_PROGRESS)
        self.assertEqual(self.action_status(process, sign), IN_PROGRESS)
        # Проверяем, что все продукты и программы вернулись в ожидание с новыми исполнениями
        for context, stage in (
            (first_product, product_stage),
            (second_product, product_stage),
            (program, program_stage),
        ):
            with self.subTest(context=context):
                self.assertEqual(self.stage_status(process, stage, context), StageInstanceStatus.PENDING)
        self.assertEqual(self.action_status(process, transfer, context=second_product), PENDING)
        self.assertEqual(self.action_instance(process, transfer, context=second_product).execution_no, 2)
        # Проверяем, что старые результаты сохранены
        self.assertEqual(ActionResult.objects.filter(action_instance__action=transfer).count(), 1)
        self.assertEqual(self.action_status(process, rollout, context=first_product), PENDING)

        self.complete(process, sign)

        # Проверяем, что после повторного подписания все контексты открылись заново
        for context, stage in (
            (first_product, product_stage),
            (second_product, product_stage),
            (program, program_stage),
        ):
            with self.subTest(context=context, after="resign"):
                self.assertEqual(self.stage_status(process, stage, context), StageInstanceStatus.IN_PROGRESS)
        self.assertEqual(self.action_status(process, transfer, context=second_product), IN_PROGRESS)

    def test_process_keeps_running_and_finishes_after_rollback(self) -> None:
        """После отката процесс продолжается и доходит до завершения."""
        process = self.reach_third_stage()
        self.cancel(process, self.third)

        process.refresh_from_db()
        # Проверяем, что процесс идёт
        self.assertEqual(process.status, WorkflowInstanceStatus.RUNNING)

        self.complete(process, self.a2)
        self.complete(process, self.a3)
        final = self.complete(process, self.a4)

        process.refresh_from_db()
        # Проверяем завершение
        self.assertTrue(final.is_workflow_completed)
        self.assertEqual(process.status, WorkflowInstanceStatus.COMPLETED)


class CancelActionTest(EngineTestCase):
    """Тесты отката отдельного действия: новое исполнение вместо отката всего этапа."""

    def setUp(self) -> None:
        """Этап с цепочкой предшественник→зависимое, независимым и необязательным действием; за ним второй этап."""
        super().setUp()
        self.stage = self.builder.stage("Этап")
        self.prerequisite_action = self.builder.action(self.stage, "Предшественник")
        self.dependent_action = self.builder.action(self.stage, "Зависимое", after=(self.prerequisite_action,))
        self.independent_action = self.builder.action(self.stage, "Независимое")
        self.optional_action = self.builder.action(self.stage, "Необязательное", optional=True)
        self.next_stage = self.builder.stage("Следующий", after=(self.stage,))
        self.next_stage_action = self.builder.action(self.next_stage, "Действие следующего этапа")

    def test_cancel_creates_new_execution_and_reactivates_action(self) -> None:
        """Откат последнего звена цепочки: новое исполнение сразу в работе, прежнее — в истории."""
        process = self.start()
        self.complete(process, self.prerequisite_action)
        self.complete(process, self.dependent_action)

        self.cancel_action(process, self.dependent_action)

        # Проверяем новое исполнение действия
        self.assertEqual(self.action_instance(process, self.dependent_action).execution_no, 2)
        self.assertEqual(self.action_status(process, self.dependent_action), IN_PROGRESS)
        # Прежнее исполнение и его результат остались
        self.assertEqual(ActionInstance.objects.filter(action=self.dependent_action).count(), 2)
        self.assertEqual(ActionResult.objects.filter(action_instance__action=self.dependent_action).count(), 1)
        # Предшественник и этап не тронуты
        self.assertEqual(self.action_status(process, self.prerequisite_action), COMPLETED)
        self.assertEqual(self.stage_status(process, self.stage), StageInstanceStatus.IN_PROGRESS)

    def test_cancel_rejects_action_that_is_not_completed(self) -> None:
        """Откатить можно только выполненное действие."""
        process = self.start()

        with self.assertRaises(InvalidStateError):
            self.cancel_action(process, self.prerequisite_action)

    def test_cancel_rejects_when_completed_dependent_exists(self) -> None:
        """Нельзя откатить действие, если от него уже зависит выполненное действие."""
        process = self.start()
        self.complete(process, self.prerequisite_action)
        self.complete(process, self.dependent_action)

        # Проверяем код ошибки
        with self.assertRaises(RuleViolationError) as raised:
            self.cancel_action(process, self.prerequisite_action)
        self.assertEqual(raised.exception.code, "has_completed_dependent")

    def test_cancel_allows_prerequisite_after_dependent_is_cancelled(self) -> None:
        """После отката зависимого действия предшественник становится последним и тоже откатывается."""
        process = self.start()
        self.complete(process, self.prerequisite_action)
        self.complete(process, self.dependent_action)

        self.cancel_action(process, self.dependent_action)
        self.cancel_action(process, self.prerequisite_action)

        # Проверяем, что предшественник получил новое исполнение и снова в работе
        self.assertEqual(self.action_instance(process, self.prerequisite_action).execution_no, 2)
        self.assertEqual(self.action_status(process, self.prerequisite_action), IN_PROGRESS)

    def test_cancel_rejects_when_stage_already_completed(self) -> None:
        """Нельзя откатить действие закрытого этапа — сначала нужно откатить сам этап."""
        process = self.start()
        self.complete(process, self.prerequisite_action)
        self.complete(process, self.dependent_action)
        self.complete(process, self.independent_action)
        self.complete(process, self.optional_action)

        self.assertEqual(self.stage_status(process, self.stage), StageInstanceStatus.COMPLETED)
        with self.assertRaises(InvalidStateError):
            self.cancel_action(process, self.independent_action)

    def test_cancel_requires_reason(self) -> None:
        """Причина обязательна."""
        process = self.start()
        self.complete(process, self.prerequisite_action)
        self.complete(process, self.dependent_action)

        # Проверяем код ошибки
        with self.assertRaises(RuleViolationError) as raised:
            self.cancel_action(process, self.dependent_action, reason="   ")
        self.assertEqual(raised.exception.code, "reason_required")

    def test_cancel_writes_journal_record(self) -> None:
        """Откат действия пишется в журнал: причина, действия, этап и автор."""
        process = self.start()
        self.complete(process, self.prerequisite_action)
        self.complete(process, self.dependent_action)
        cancelled_instance = self.action_instance(process, self.dependent_action)

        outcome = self.cancel_action(process, self.dependent_action, reason="Ошиблись в данных")

        record = ActionRollback.objects.get()
        # Проверяем запись журнала
        self.assertEqual(outcome.rollback, record)
        self.assertEqual(record.reason, "Ошиблись в данных")
        self.assertEqual(record.workflow_instance, process)
        self.assertEqual(record.stage_instance, self.stage_instance(process, self.stage))
        self.assertEqual(record.from_action_instance, cancelled_instance)
        self.assertEqual(record.to_action_instance, self.action_instance(process, self.dependent_action))
        self.assertEqual(record.created_by, self.user)

    def test_cancel_rejects_not_latest_execution(self) -> None:
        """Откатить можно только последнее исполнение действия."""
        process = self.start()
        self.complete(process, self.prerequisite_action)
        self.complete(process, self.dependent_action)
        first_execution = ActionInstance.objects.get(action=self.dependent_action, execution_no=1)
        self.cancel_action(process, self.dependent_action)
        self.complete(process, self.dependent_action)

        with self.assertRaises(InvalidStateError):
            engine.cancel_action(action_instance=first_execution, reason="Ошибка", cancelled_by=self.user)

    def test_cancel_optional_action_does_not_affect_others(self) -> None:
        """Необязательное действие без зависимостей: откат не трогает остальные действия и этап."""
        process = self.start()
        self.complete(process, self.optional_action)

        self.cancel_action(process, self.optional_action)

        # Проверяем новое исполнение необязательного действия
        self.assertEqual(self.action_instance(process, self.optional_action).execution_no, 2)
        self.assertEqual(self.action_status(process, self.optional_action), IN_PROGRESS)
        # Остальные действия и этап не тронуты
        self.assertEqual(self.action_status(process, self.prerequisite_action), IN_PROGRESS)
        self.assertEqual(self.stage_status(process, self.stage), StageInstanceStatus.IN_PROGRESS)


class CancelActionTransitionOnlyTest(EngineTestCase):
    """Откат действия, запускаемого только переходом: новое исполнение ждёт нового перехода."""

    def setUp(self) -> None:
        """Этап с действием-триггером и целевым действием, запускаемым только по его исходу."""
        super().setUp()
        self.stage = self.builder.stage("Этап")
        self.trigger = self.builder.action(self.stage, "Триггер")
        self.target = self.builder.action(self.stage, "Цель", trigger_only=True)
        self.other = self.builder.action(self.stage, "Другое")
        outcome = self.builder.outcome(self.trigger, "go")
        self.builder.branch(outcome, self.target)

    def test_cancel_new_execution_stays_pending_until_triggered_again(self) -> None:
        """Новое исполнение не запускается само: у него нет метки запуска переходом."""
        process = self.start()
        self.complete(process, self.trigger, code="go")
        self.complete(process, self.target)
        self.assertEqual(self.action_status(process, self.target), COMPLETED)

        self.cancel_action(process, self.target)

        instance = self.action_instance(process, self.target)
        # Проверяем, что новое исполнение ждёт перехода, а не запущено сразу
        self.assertEqual(instance.execution_no, 2)
        self.assertEqual(instance.status, PENDING)
        self.assertIsNone(instance.triggered_at)
