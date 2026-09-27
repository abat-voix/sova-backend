from datetime import timedelta

from django.conf import settings
from django.core import mail
from django.test import TestCase
from django.utils import timezone

from sova.interactions.tests.factories import ResponsibleFactory
from sova.notifications.models import DeadlineDelivery, NotifySettings
from sova.processes.tasks import notify_deadlines
from sova.processes.tests.factories import ActionInstanceFactory


class NotifyDeadlinesTaskTest(TestCase):
    """Сквозной прогон задачи уведомлений о сроках."""

    def test_task_notifies_responsible_about_overdue_action(self) -> None:
        """Просроченное действие — письмо КАМу и запись в журнале; повторный запуск молчит."""
        NotifySettings.objects.update(is_channel_telegram=False, is_channel_max=False, is_channel_system=False)
        instance = ActionInstanceFactory(
            action__default_duration_days=5,
            planned_end=timezone.now() - timedelta(days=2),
        )
        responsible = ResponsibleFactory(interaction=instance.stage_instance.workflow_instance.interaction)
        instance.responsible = responsible.manager
        instance.save(update_fields=["responsible"])

        stats = notify_deadlines()
        notify_deadlines()

        # Проверяем одно письмо КАМу: сводка по действию и по его этапу
        self.assertEqual([message.to for message in mail.outbox], [[responsible.manager.email]])
        self.assertIn(instance.action_name_snapshot, mail.outbox[0].body)
        # Проверяем журнал: действие и этап
        self.assertEqual(DeadlineDelivery.objects.count(), 2)
        # Проверяем статистику первого запуска
        self.assertEqual(stats["sent"], 1)

    def test_beat_schedule_runs_task_daily(self) -> None:
        """Задача в расписании beat на OVERDUE_NOTIFY_HOUR:00."""
        entry = settings.CELERY_BEAT_SCHEDULE["notify-deadlines"]

        # Проверяем имя задачи
        self.assertEqual(entry["task"], "sova.processes.tasks.notify_deadlines")
        # Проверяем час и минуту запуска
        self.assertEqual(entry["schedule"].hour, {settings.OVERDUE_NOTIFY_HOUR})
        self.assertEqual(entry["schedule"].minute, {0})
