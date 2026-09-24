import uuid
from dataclasses import replace
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.core import mail
from django.test import TestCase

from sova.core.tests.factories import UserFactory
from sova.notifications.enum import DeliveryMode, NotificationChannel, NotificationKind, NotifyEvent, NotifyType
from sova.notifications.models import DeadlineDelivery, Notification, NotifySettings
from sova.notifications.services.deadline_dispatch import DeadlineDispatchService
from sova.processes.services.deadlines import DeadlineItem

# Четверг, 09:00 МСК
THURSDAY = datetime(2026, 10, 15, 9, 0, tzinfo=ZoneInfo("Europe/Moscow"))


class DeadlineDispatchTest(TestCase):
    """Тесты доставки уведомлений о сроках и журнала."""

    def setUp(self) -> None:
        """Все правила: только email, чтобы проверять через mail.outbox."""
        NotifySettings.objects.update(is_channel_telegram=False, is_channel_max=False, is_channel_system=False)
        self.kam = UserFactory()
        self.head = UserFactory()

    def item(self, kind=NotifyType.ACTION_DEADLINE, event=NotifyEvent.OVERDUE, recipients=None, deadline=None) -> DeadlineItem:
        """Пункт, просроченный на сутки."""
        return DeadlineItem(
            notify_type=kind,
            event=event,
            object_id=uuid.uuid4(),
            deadline=deadline or THURSDAY - timedelta(days=1),
            counterparty="МГУ",
            workflow_name="B2B",
            stage_name="Этап",
            action_name="Действие",
            recipients=tuple(recipients or [self.kam]),
        )

    def dispatch(self, items, now=THURSDAY) -> dict:
        """Запуск рассылки."""
        return DeadlineDispatchService().dispatch(items=items, now=now)

    def test_digest_is_one_message_per_recipient(self) -> None:
        """Сводка: одно письмо на получателя с пунктами разных видов, журнал по каждому пункту."""
        items = [self.item(), self.item(kind=NotifyType.STAGE_DEADLINE, recipients=[self.kam, self.head])]

        stats = self.dispatch(items)

        # Проверяем число писем: КАМу одно на оба пункта, руководителю одно
        self.assertEqual(sorted(message.to[0] for message in mail.outbox), sorted([self.kam.email, self.head.email]))
        # Проверяем, что сводка КАМа содержит оба пункта
        kam_mail = next(message for message in mail.outbox if message.to == [self.kam.email])
        self.assertIn("просрочено 2", kam_mail.subject)
        # Проверяем журнал: 2 пункта КАМа + 1 руководителя
        self.assertEqual(DeadlineDelivery.objects.count(), 3)
        # Проверяем статистику
        self.assertEqual(stats, {"items": 2, "messages": 2, "sent": 2, "failed": 0})

    def test_separate_mode_sends_message_per_item(self) -> None:
        """delivery_mode=separate — отдельное письмо на каждый пункт."""
        NotifySettings.objects.filter(notify_type=NotifyType.ACTION_DEADLINE).update(delivery_mode=DeliveryMode.SEPARATE)

        self.dispatch([self.item(), self.item()])

        # Проверяем два отдельных письма
        self.assertEqual(len(mail.outbox), 2)
        self.assertTrue(mail.outbox[0].subject.startswith("СОВА: просрочено — действие"))

    def test_second_run_sends_nothing(self) -> None:
        """Повторный запуск без repeat_every_days ничего не шлёт."""
        items = [self.item()]
        self.dispatch(items)

        stats = self.dispatch(items, now=THURSDAY + timedelta(days=1))

        # Проверяем, что письмо было одно
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(stats["messages"], 0)

    def test_repeat_every_days_uses_calendar_days(self) -> None:
        """Повтор через сутки срабатывает на следующий запуск, даже если он на секунды «раньше» суток."""
        NotifySettings.objects.filter(notify_type=NotifyType.ACTION_DEADLINE).update(repeat_every_days=1)
        items = [self.item()]
        self.dispatch(items, now=THURSDAY + timedelta(seconds=3))

        self.dispatch(items, now=THURSDAY + timedelta(days=1, seconds=1))

        # Проверяем, что ушло второе письмо
        self.assertEqual(len(mail.outbox), 2)
        # Проверяем счётчик отправок в журнале
        self.assertEqual(DeadlineDelivery.objects.get().send_count, 2)

    def test_repeat_waits_for_interval(self) -> None:
        """repeat_every_days=3 — на следующий день повтора нет."""
        NotifySettings.objects.filter(notify_type=NotifyType.ACTION_DEADLINE).update(repeat_every_days=3)
        items = [self.item()]
        self.dispatch(items)

        self.dispatch(items, now=THURSDAY + timedelta(days=1))

        # Проверяем, что письмо одно
        self.assertEqual(len(mail.outbox), 1)

    def test_reminder_is_sent_once_even_with_repeat(self) -> None:
        """Предупреждение не повторяется, даже если задан repeat_every_days."""
        NotifySettings.objects.filter(notify_type=NotifyType.ACTION_DEADLINE).update(repeat_every_days=1)
        items = [self.item(event=NotifyEvent.REMINDER, deadline=THURSDAY + timedelta(days=3))]
        self.dispatch(items)

        self.dispatch(items, now=THURSDAY + timedelta(days=1))

        # Проверяем, что письмо одно
        self.assertEqual(len(mail.outbox), 1)

    def test_new_deadline_of_same_object_is_sent_again(self) -> None:
        """Тот же объект с пересчитанным сроком — новая просрочка, новое письмо."""
        first = self.item()
        self.dispatch([first])
        moved = replace(first, deadline=first.deadline + timedelta(hours=5))

        self.dispatch([moved], now=THURSDAY + timedelta(days=1))

        # Проверяем, что ушло второе письмо
        self.assertEqual(len(mail.outbox), 2)

    def test_new_recipient_gets_already_notified_item(self) -> None:
        """Новый ответственный получает уже отправленный прежнему пункт, прежний — нет."""
        first = self.item()
        self.dispatch([first])
        new_kam = UserFactory()
        reassigned = replace(first, recipients=(new_kam,))

        self.dispatch([reassigned], now=THURSDAY + timedelta(days=1))

        # Проверяем адресата второго письма
        self.assertEqual([message.to for message in mail.outbox], [[self.kam.email], [new_kam.email]])

    @patch("sova.notifications.services.channels.email.send_mail", side_effect=OSError("smtp down"))
    def test_failed_send_does_not_write_journal(self, send_mail) -> None:
        """Неудачная отправка не пишет журнал — следующий запуск повторит."""
        stats = self.dispatch([self.item()])

        # Проверяем, что журнал пуст
        self.assertFalse(DeadlineDelivery.objects.exists())
        # Проверяем статистику
        self.assertEqual(stats["failed"], 1)

    def test_recipient_without_address_in_enabled_channels(self) -> None:
        """Только Telegram включён, а chat id у получателя нет — неудача без исключений и без журнала."""
        NotifySettings.objects.update(is_channel_email=False, is_channel_telegram=True)

        stats = self.dispatch([self.item()])

        # Проверяем, что ничего не записано и неудача учтена
        self.assertFalse(DeadlineDelivery.objects.exists())
        self.assertEqual(stats["failed"], 1)

    def test_rule_without_channels_builds_no_messages(self) -> None:
        """Все каналы выключены — сообщений нет, неудач нет."""
        NotifySettings.objects.update(is_channel_email=False)

        stats = self.dispatch([self.item()])

        # Проверяем статистику
        self.assertEqual(stats, {"items": 1, "messages": 0, "sent": 0, "failed": 0})

    def test_skip_weekends(self) -> None:
        """is_skip_weekends: в субботу не шлёт, в понедельник шлёт."""
        NotifySettings.objects.filter(notify_type=NotifyType.ACTION_DEADLINE).update(is_skip_weekends=True)
        items = [self.item()]

        self.dispatch(items, now=THURSDAY + timedelta(days=2))

        # Проверяем, что в субботу писем нет
        self.assertEqual(len(mail.outbox), 0)

        self.dispatch(items, now=THURSDAY + timedelta(days=4))

        # Проверяем, что в понедельник письмо ушло
        self.assertEqual(len(mail.outbox), 1)

    def test_system_channel_creates_notification_and_journal_row(self) -> None:
        """Email и системный канал: письмо, уведомление в системе и по строке журнала на канал."""
        NotifySettings.objects.update(is_channel_system=True)

        stats = self.dispatch([self.item()])

        # Проверяем письмо
        self.assertEqual(len(mail.outbox), 1)
        # Проверяем уведомление в системе, его группу и заголовок без префикса — префикс остаётся только в письме
        self.assertEqual(Notification.objects.get().recipient, self.kam)
        self.assertEqual(Notification.objects.get().title, "Просрочено — действие")
        self.assertTrue(mail.outbox[0].subject.startswith("СОВА: сроки"))
        self.assertEqual(Notification.objects.get().kind, NotificationKind.DEADLINE)
        # Проверяем журнал по каналам
        self.assertEqual(
            sorted(DeadlineDelivery.objects.values_list("channel", flat=True)),
            [NotificationChannel.EMAIL, NotificationChannel.SYSTEM],
        )
        # Проверяем статистику: сообщение на каждый канал
        self.assertEqual(stats, {"items": 1, "messages": 2, "sent": 2, "failed": 0})

    def test_failed_email_is_retried_without_duplicate_system_notification(self) -> None:
        """Email упал, система — нет: следующий запуск шлёт только email, второго уведомления в системе нет."""
        NotifySettings.objects.update(is_channel_system=True)
        items = [self.item()]
        with patch("sova.notifications.services.channels.email.send_mail", side_effect=OSError("smtp down")):
            first = self.dispatch(items)

        second = self.dispatch(items, now=THURSDAY + timedelta(hours=1))

        # Проверяем первый запуск: система дошла, email нет
        self.assertEqual(first, {"items": 1, "messages": 2, "sent": 1, "failed": 1})
        # Проверяем второй запуск: только email
        self.assertEqual(second, {"items": 1, "messages": 1, "sent": 1, "failed": 0})
        # Проверяем, что уведомление в системе одно
        self.assertEqual(Notification.objects.count(), 1)
        # Проверяем, что письмо ушло со второго раза
        self.assertEqual(len(mail.outbox), 1)

    def test_system_channel_sends_item_per_notification_with_link(self) -> None:
        """Сводка по email одна, а в колокольчике — уведомление на каждый пункт со своей ссылкой."""
        NotifySettings.objects.update(is_channel_system=True)
        first = replace(self.item(), interaction_id=uuid.uuid4(), workflow_instance_id=uuid.uuid4())
        second = replace(self.item(), interaction_id=uuid.uuid4(), workflow_instance_id=uuid.uuid4())

        stats = self.dispatch([first, second])

        # Проверяем одно письмо-сводку
        self.assertEqual(len(mail.outbox), 1)
        # Проверяем два уведомления в колокольчике со ссылками на свои действия
        self.assertEqual(
            sorted(Notification.objects.values_list("link", flat=True)),
            sorted(
                f"/interactions?interaction={entry.interaction_id}&process={entry.workflow_instance_id}"
                f"&action={entry.object_id}"
                for entry in (first, second)
            ),
        )
        # Проверяем статистику: письмо + два уведомления
        self.assertEqual(stats, {"items": 2, "messages": 3, "sent": 3, "failed": 0})
