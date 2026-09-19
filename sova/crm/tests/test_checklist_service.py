from django.test import TestCase

from sova.crm.models import InstanceChecklistProgress
from sova.crm.services import ChecklistService
from sova.crm.tests.factories import (
    StatusChecklistItemFactory,
    UserFactory,
    WorkflowInstanceFactory,
    WorkflowStatusFactory,
)


class GetOrCreateProgressTestCase(TestCase):
    """Тесты ChecklistService.get_or_create_progress."""

    def test_creates_progress_rows_for_active_items_of_current_status(self) -> None:
        """Для активных пунктов текущего статуса создаются строки прогресса."""
        status = WorkflowStatusFactory()
        item1 = StatusChecklistItemFactory(status=status, order=1)
        item2 = StatusChecklistItemFactory(status=status, order=2)
        instance = WorkflowInstanceFactory(current_status=status)

        progress = ChecklistService.get_or_create_progress(instance)

        self.assertEqual({p.checklist_item_id for p in progress}, {item1.id, item2.id})
        self.assertEqual(InstanceChecklistProgress.objects.filter(instance=instance).count(), 2)

    def test_ignores_inactive_items(self) -> None:
        """Неактивные (soft-deleted) пункты чек-листа не получают строку прогресса."""
        status = WorkflowStatusFactory()
        StatusChecklistItemFactory(status=status, order=1, is_active=False)
        instance = WorkflowInstanceFactory(current_status=status)

        progress = ChecklistService.get_or_create_progress(instance)

        self.assertEqual(progress, [])

    def test_second_call_does_not_duplicate_rows(self) -> None:
        """Повторный вызов для того же статуса не создаёт дубликаты строк прогресса."""
        status = WorkflowStatusFactory()
        StatusChecklistItemFactory(status=status, order=1)
        instance = WorkflowInstanceFactory(current_status=status)

        ChecklistService.get_or_create_progress(instance)
        ChecklistService.get_or_create_progress(instance)

        self.assertEqual(InstanceChecklistProgress.objects.filter(instance=instance).count(), 1)

    def test_lazy_only_current_status_not_whole_template(self) -> None:
        """Прогресс создаётся только для текущего статуса, не для всех статусов шаблона сразу."""
        current_status = WorkflowStatusFactory()
        other_status = WorkflowStatusFactory(template=current_status.template)
        StatusChecklistItemFactory(status=current_status)
        StatusChecklistItemFactory(status=other_status)
        instance = WorkflowInstanceFactory(template=current_status.template, current_status=current_status)

        progress = ChecklistService.get_or_create_progress(instance)

        self.assertEqual(len(progress), 1)


class ToggleTestCase(TestCase):
    """Тесты ChecklistService.toggle."""

    def test_marks_item_done_with_user_and_timestamp(self) -> None:
        """Отметка выполненным проставляет done_at и done_by."""
        instance = WorkflowInstanceFactory()
        item = StatusChecklistItemFactory(status=instance.current_status)
        user = UserFactory()

        progress = ChecklistService.toggle(instance, item.id, user, is_done=True)

        self.assertTrue(progress.is_done)
        self.assertIsNotNone(progress.done_at)
        self.assertEqual(progress.done_by, user)

    def test_unmarking_clears_timestamp_and_user(self) -> None:
        """Снятие отметки очищает done_at/done_by."""
        instance = WorkflowInstanceFactory()
        item = StatusChecklistItemFactory(status=instance.current_status)
        user = UserFactory()
        ChecklistService.toggle(instance, item.id, user, is_done=True)

        progress = ChecklistService.toggle(instance, item.id, user, is_done=False)

        self.assertFalse(progress.is_done)
        self.assertIsNone(progress.done_at)
        self.assertIsNone(progress.done_by)


class IsCompleteTestCase(TestCase):
    """Тесты ChecklistService.is_complete."""

    def test_true_when_no_checklist_items(self) -> None:
        """У статуса без пунктов чек-листа заявка считается готовой к переходу."""
        instance = WorkflowInstanceFactory()

        self.assertTrue(ChecklistService.is_complete(instance))

    def test_false_when_some_items_not_done(self) -> None:
        """Не все пункты отмечены — чек-лист не завершён."""
        instance = WorkflowInstanceFactory()
        item1 = StatusChecklistItemFactory(status=instance.current_status, order=1)
        StatusChecklistItemFactory(status=instance.current_status, order=2)
        ChecklistService.toggle(instance, item1.id, UserFactory(), is_done=True)

        self.assertFalse(ChecklistService.is_complete(instance))

    def test_true_when_all_active_items_done(self) -> None:
        """Все активные пункты отмечены — чек-лист завершён."""
        instance = WorkflowInstanceFactory()
        item1 = StatusChecklistItemFactory(status=instance.current_status, order=1)
        item2 = StatusChecklistItemFactory(status=instance.current_status, order=2)
        user = UserFactory()
        ChecklistService.toggle(instance, item1.id, user, is_done=True)
        ChecklistService.toggle(instance, item2.id, user, is_done=True)

        self.assertTrue(ChecklistService.is_complete(instance))

    def test_inactive_item_not_required(self) -> None:
        """Неактивный пункт не учитывается при проверке завершённости."""
        instance = WorkflowInstanceFactory()
        StatusChecklistItemFactory(status=instance.current_status, is_active=False)

        self.assertTrue(ChecklistService.is_complete(instance))
