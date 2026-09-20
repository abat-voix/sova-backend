import uuid

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from sova.core.tests.factories import UserFactory
from sova.processes.enum import (
    ActionInstanceStatus,
    RollbackMode,
    StageInstanceContextType,
    StageInstanceStatus,
    WorkflowInstanceStatus,
)
from sova.processes.models import ActionInstance, StageInstance, StageRollback, WorkflowInstance
from sova.processes.tests.factories import (
    ActionInstanceFactory,
    StageInstanceFactory,
    StageRollbackFactory,
    WorkflowInstanceFactory,
)


def relation_names(model) -> list[str]:
    """Имена связанных полей модели: при проверке значений полей их наличие в базе не важно."""
    return [field.name for field in model._meta.fields if field.is_relation]


class StatusValuesTest(TestCase):
    """Тесты статусов: допустимые значения фиксированы перечислениями, а не произвольными строками."""

    def test_workflow_instance_statuses(self) -> None:
        """У процесса два статуса: идёт и завершён."""
        # Проверяем значения перечисления
        self.assertEqual({value for value, _ in WorkflowInstanceStatus.choices}, {"running", "completed"})

    def test_stage_and_action_statuses(self) -> None:
        """Этап и действие бывают ожидающими, в работе и завершёнными."""
        expected = {"pending", "in_progress", "completed"}
        # Проверяем значения обоих перечислений
        self.assertEqual({value for value, _ in StageInstanceStatus.choices}, expected)
        self.assertEqual({value for value, _ in ActionInstanceStatus.choices}, expected)

    def test_status_fields_use_enum_choices(self) -> None:
        """Поле статуса каждой модели ограничено своим перечислением."""
        # Проверяем, что модели подключили перечисления
        self.assertEqual(WorkflowInstance._meta.get_field("status").choices, WorkflowInstanceStatus.choices)
        self.assertEqual(StageInstance._meta.get_field("status").choices, StageInstanceStatus.choices)
        self.assertEqual(ActionInstance._meta.get_field("status").choices, ActionInstanceStatus.choices)

    def test_status_defaults(self) -> None:
        """Процесс по умолчанию идёт, этап и действие ожидают."""
        # Проверяем значения по умолчанию
        self.assertEqual(WorkflowInstance._meta.get_field("status").default, WorkflowInstanceStatus.RUNNING)
        self.assertEqual(StageInstance._meta.get_field("status").default, StageInstanceStatus.PENDING)
        self.assertEqual(ActionInstance._meta.get_field("status").default, ActionInstanceStatus.PENDING)

    def test_arbitrary_status_is_rejected(self) -> None:
        """Произвольная строка вместо статуса не проходит валидацию модели."""
        builds = (
            WorkflowInstanceFactory.build(status="paused"),
            StageInstanceFactory.build(status="done"),
            ActionInstanceFactory.build(status="done"),
        )
        for instance in builds:
            with self.subTest(model=type(instance).__name__):
                # Проверяем ошибку по полю status
                with self.assertRaises(ValidationError) as raised:
                    instance.clean_fields(exclude=relation_names(type(instance)))
                self.assertIn("status", raised.exception.message_dict)


class StageInstanceStartTimeTest(TestCase):
    """Тесты момента открытия этапа: он отличается от момента создания экземпляра."""

    def test_start_time_is_empty_until_stage_is_opened(self) -> None:
        """Пока этап не открыт, момента открытия нет."""
        stage_instance = StageInstanceFactory()
        # Проверяем пустое значение
        self.assertIsNone(stage_instance.started_at)

    def test_start_time_is_stored(self) -> None:
        """Момент открытия сохраняется в базе."""
        opened_at = timezone.now()
        stage_instance = StageInstanceFactory(started_at=opened_at)

        stage_instance.refresh_from_db()

        # Проверяем, что значение не потерялось
        self.assertEqual(stage_instance.started_at, opened_at)


class StageInstanceUniquenessTest(TestCase):
    """Тесты уникальности экземпляра этапа: один этап на один контекст внутри процесса."""

    def test_same_stage_cannot_be_created_twice_for_one_context(self) -> None:
        """Повторный экземпляр этапа для того же продукта отвергается базой."""
        context_id = uuid.uuid4()
        first = StageInstanceFactory(context_type=StageInstanceContextType.IT_PRODUCT, context_id=context_id)

        # Проверяем, что база отвергает дубликат
        with self.assertRaises(IntegrityError), transaction.atomic():
            StageInstanceFactory(
                workflow_instance=first.workflow_instance,
                stage=first.stage,
                context_type=StageInstanceContextType.IT_PRODUCT,
                context_id=context_id,
            )

    def test_stage_without_context_cannot_be_created_twice(self) -> None:
        """Этап без контекста тоже не дублируется: NULL в уникальном ограничении не считается разным значением."""
        first = StageInstanceFactory(context_id=None)

        # Проверяем, что база отвергает дубликат
        with self.assertRaises(IntegrityError), transaction.atomic():
            StageInstanceFactory(
                workflow_instance=first.workflow_instance,
                stage=first.stage,
                context_id=None,
            )

    def test_same_stage_is_allowed_for_different_contexts(self) -> None:
        """Один этап продукта создаётся отдельно для каждого продукта."""
        first = StageInstanceFactory(context_type=StageInstanceContextType.IT_PRODUCT, context_id=uuid.uuid4())

        second = StageInstanceFactory(
            workflow_instance=first.workflow_instance,
            stage=first.stage,
            context_type=StageInstanceContextType.IT_PRODUCT,
            context_id=uuid.uuid4(),
        )

        # Проверяем, что оба экземпляра существуют
        self.assertEqual(StageInstance.objects.filter(stage=first.stage).count(), 2)
        self.assertNotEqual(first.pk, second.pk)

    def test_context_lookup_has_an_index(self) -> None:
        """Выборка экземпляров по контексту идёт по индексу."""
        indexed = [tuple(index.fields) for index in StageInstance._meta.indexes]
        # Проверяем наличие индекса по типу и id контекста
        self.assertIn(("context_type", "context_id"), indexed)


class ActionInstanceUniquenessTest(TestCase):
    """Тесты уникальности экземпляра действия: номер исполнения не повторяется."""

    def test_same_execution_cannot_be_created_twice(self) -> None:
        """Два исполнения одного действия с одним номером отвергаются базой."""
        first = ActionInstanceFactory()

        # Проверяем, что база отвергает дубликат
        with self.assertRaises(IntegrityError), transaction.atomic():
            ActionInstanceFactory(
                stage_instance=first.stage_instance,
                action=first.action,
                execution_no=first.execution_no,
            )

    def test_repeat_execution_gets_next_number(self) -> None:
        """Повторное исполнение действия допустимо под следующим номером."""
        first = ActionInstanceFactory()

        repeat = ActionInstanceFactory(
            stage_instance=first.stage_instance,
            action=first.action,
            execution_no=first.execution_no + 1,
        )

        # Проверяем, что оба исполнения сохранены
        self.assertEqual(ActionInstance.objects.filter(action=first.action).count(), 2)
        self.assertEqual(repeat.execution_no, 2)


class WorkflowInstanceUniquenessTest(TestCase):
    """Тесты уникальности процесса: один workflow запускается для взаимодействия один раз."""

    def test_workflow_cannot_be_started_twice_for_one_interaction(self) -> None:
        """Второй процесс того же workflow для того же взаимодействия отвергается базой."""
        first = WorkflowInstanceFactory()

        # Проверяем, что база отвергает дубликат
        with self.assertRaises(IntegrityError), transaction.atomic():
            WorkflowInstanceFactory(workflow=first.workflow, interaction=first.interaction)

    def test_same_workflow_is_allowed_for_another_interaction(self) -> None:
        """Один workflow можно запускать для разных взаимодействий."""
        first = WorkflowInstanceFactory()

        WorkflowInstanceFactory(workflow=first.workflow)

        # Проверяем, что оба процесса существуют
        self.assertEqual(WorkflowInstance.objects.filter(workflow=first.workflow).count(), 2)


class StageRollbackTest(TestCase):
    """Тесты журнала откатов: кто, когда, зачем и откуда куда вернул процесс."""

    def test_rollback_is_recorded_with_time(self) -> None:
        """Запись об откате получает время создания."""
        rollback = StageRollbackFactory()
        # Проверяем, что время проставилось
        self.assertIsNotNone(rollback.created_at)

    def test_modes(self) -> None:
        """Режимов отката два: заново и только последнее действие."""
        # Проверяем значения перечисления
        self.assertEqual({value for value, _ in RollbackMode.choices}, {"restart", "last_only"})

    def test_arbitrary_mode_is_rejected(self) -> None:
        """Произвольный режим не проходит валидацию модели."""
        rollback = StageRollbackFactory.build(mode="skip")

        # Проверяем ошибку по полю mode
        with self.assertRaises(ValidationError) as raised:
            rollback.clean_fields(exclude=relation_names(StageRollback))
        self.assertIn("mode", raised.exception.message_dict)

    def test_reason_is_required(self) -> None:
        """Причина отката обязательна."""
        rollback = StageRollbackFactory.build(reason="")

        # Проверяем ошибку по полю reason
        with self.assertRaises(ValidationError) as raised:
            rollback.clean_fields(exclude=relation_names(StageRollback))
        self.assertIn("reason", raised.exception.message_dict)

    def test_clean_accepts_stage_instances_of_the_same_process(self) -> None:
        """Оба экземпляра этапа принадлежат процессу записи — проверка проходит."""
        rollback = StageRollbackFactory()
        # Проверяем, что исключения нет
        rollback.clean()

    def test_clean_rejects_cancelled_stage_from_another_process(self) -> None:
        """Отменённый этап другого процесса не проходит проверку."""
        process = WorkflowInstanceFactory()
        rollback = StageRollback(
            workflow_instance=process,
            from_stage_instance=StageInstanceFactory(),
            to_stage_instance=StageInstanceFactory(workflow_instance=process),
            reason="Ошибка",
            mode=RollbackMode.RESTART,
        )

        # Проверяем ошибку по полю from_stage_instance
        with self.assertRaises(ValidationError) as raised:
            rollback.clean()
        self.assertIn("from_stage_instance", raised.exception.message_dict)

    def test_clean_rejects_target_stage_from_another_process(self) -> None:
        """Этап возврата из другого процесса не проходит проверку."""
        process = WorkflowInstanceFactory()
        rollback = StageRollback(
            workflow_instance=process,
            from_stage_instance=StageInstanceFactory(workflow_instance=process),
            to_stage_instance=StageInstanceFactory(),
            reason="Ошибка",
            mode=RollbackMode.RESTART,
        )

        # Проверяем ошибку по полю to_stage_instance
        with self.assertRaises(ValidationError) as raised:
            rollback.clean()
        self.assertIn("to_stage_instance", raised.exception.message_dict)

    def test_clean_rejects_rollback_to_the_same_stage(self) -> None:
        """Откат на тот же самый экземпляр этапа бессмыслен."""
        process = WorkflowInstanceFactory()
        stage_instance = StageInstanceFactory(workflow_instance=process)
        rollback = StageRollback(
            workflow_instance=process,
            from_stage_instance=stage_instance,
            to_stage_instance=stage_instance,
            reason="Ошибка",
            mode=RollbackMode.RESTART,
        )

        # Проверяем ошибку по полю to_stage_instance
        with self.assertRaises(ValidationError) as raised:
            rollback.clean()
        self.assertIn("to_stage_instance", raised.exception.message_dict)

    def test_newest_rollback_comes_first(self) -> None:
        """Записи журнала отдаются от новых к старым."""
        older = StageRollbackFactory()
        newer = StageRollbackFactory()

        # Проверяем порядок
        self.assertEqual(list(StageRollback.objects.all()), [newer, older])

    def test_deleting_author_keeps_the_record(self) -> None:
        """Удаление пользователя не стирает запись журнала."""
        author = UserFactory()
        rollback = StageRollbackFactory(created_by=author)

        author.delete()
        rollback.refresh_from_db()

        # Проверяем, что запись осталась без автора
        self.assertIsNone(rollback.created_by)

    def test_deleting_process_deletes_its_journal(self) -> None:
        """Журнал откатов удаляется вместе с процессом."""
        rollback = StageRollbackFactory()

        rollback.workflow_instance.delete()

        # Проверяем, что записи больше нет
        self.assertFalse(StageRollback.objects.filter(pk=rollback.pk).exists())


class ActionInstanceTriggerTimeTest(TestCase):
    """Тесты момента запуска переходом: по нему отличают запущенное, но ждущее зависимостей действие."""

    def test_trigger_time_is_empty_by_default(self) -> None:
        """Действие, которое никто не запускал переходом, момента запуска не имеет."""
        action_instance = ActionInstanceFactory()
        # Проверяем пустое значение
        self.assertIsNone(action_instance.triggered_at)

    def test_trigger_time_is_stored(self) -> None:
        """Момент запуска переходом сохраняется в базе."""
        triggered_at = timezone.now()
        action_instance = ActionInstanceFactory(triggered_at=triggered_at)

        action_instance.refresh_from_db()

        # Проверяем, что значение не потерялось
        self.assertEqual(action_instance.triggered_at, triggered_at)
