from django.test import TestCase

from crm.tests.factories import StatusChecklistItemFactory, WorkflowStatusFactory


class EffectiveStaleThresholdDaysTestCase(TestCase):
    """Тесты StatusChecklistItem.effective_stale_threshold_days."""

    def test_uses_own_value_when_set(self) -> None:
        """Свой порог пункта имеет приоритет над порогом статуса."""
        status = WorkflowStatusFactory(stale_threshold_days=14)
        item = StatusChecklistItemFactory(status=status, stale_threshold_days=3)

        self.assertEqual(item.effective_stale_threshold_days, 3)

    def test_falls_back_to_status_value_when_own_is_none(self) -> None:
        """Без своего порога — используется порог статуса, считаемый от created_at пункта."""
        status = WorkflowStatusFactory(stale_threshold_days=14)
        item = StatusChecklistItemFactory(status=status, stale_threshold_days=None)

        self.assertEqual(item.effective_stale_threshold_days, 14)

    def test_none_when_neither_item_nor_status_has_threshold(self) -> None:
        """Ни у пункта, ни у статуса порога нет — проверки зависания для пункта не будет."""
        status = WorkflowStatusFactory(stale_threshold_days=None)
        item = StatusChecklistItemFactory(status=status, stale_threshold_days=None)

        self.assertIsNone(item.effective_stale_threshold_days)
