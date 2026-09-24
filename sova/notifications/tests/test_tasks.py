from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from sova.notifications.models import Notification
from sova.notifications.tasks import cleanup_notifications
from sova.notifications.tests.factories import NotificationFactory


@override_settings(NOTIFICATIONS_RETENTION_DAYS=60)
class CleanupNotificationsTest(TestCase):
    """Тесты задачи cleanup_notifications."""

    def test_deletes_only_older_than_retention(self) -> None:
        """Удаляются уведомления старше срока хранения — прочитанные и нет; свежие остаются."""
        old_unread = NotificationFactory()
        old_read = NotificationFactory(is_read=True)
        fresh = NotificationFactory()
        Notification.objects.filter(pk__in=[old_unread.pk, old_read.pk]).update(
            created_at=timezone.now() - timedelta(days=61),
        )

        deleted = cleanup_notifications()

        # Проверяем число удалённых
        self.assertEqual(deleted, 2)
        # Проверяем, что осталось только свежее
        self.assertEqual(list(Notification.objects.all()), [fresh])
