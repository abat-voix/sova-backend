from unittest.mock import call, patch

from django.core import mail
from django.db import transaction
from django.test import TestCase

from sova.core.tests.factories import UserFactory
from sova.notifications.enum import NotificationChannel, NotificationKind, NotifyType
from sova.notifications.models import Notification, NotifySettings
from sova.notifications.services.event_notification import event_notification_service
from sova.notifications.services.message import Message
from sova.notifications.tasks import send_event_notification

EXTERNAL = [NotificationChannel.EMAIL, NotificationChannel.TELEGRAM, NotificationChannel.MAX]


@patch("sova.notifications.services.event_notification.send_event_notification")
class EventNotificationServiceTest(TestCase):
    """Отбор получателей и каналов по настройкам типа и постановка задачи после фиксации транзакции."""

    def setUp(self) -> None:
        """КАМ и руководитель; у типа назначения КАМа по умолчанию — только ответственному, все каналы."""
        self.kam = UserFactory()
        self.head = UserFactory()
        self.message = Message(text="Вас назначили КАМом — МГУ", link="/interactions?interaction=1")

    def notify(self, **kwargs) -> None:
        """Вызов notify для назначения КАМа с выполнением on_commit."""
        with self.captureOnCommitCallbacks(execute=True):
            event_notification_service.notify(notify_type=NotifyType.KAM_ASSIGNED, message=self.message, **kwargs)

    def set_rule(self, **values) -> None:
        """Меняет строку настроек назначения КАМа."""
        NotifySettings.objects.filter(notify_type=NotifyType.KAM_ASSIGNED).update(**values)

    def test_sends_to_responsible_by_channel_groups(self, task) -> None:
        """Ответственному: колокольчик без префикса, внешние каналы с «СОВА:», группа «Назначения»."""
        self.notify(responsible=self.kam, head=self.head)

        # Проверяем две постановки: колокольчик и внешние каналы
        self.assertEqual(
            task.delay.call_args_list,
            [
                call(
                    user_ids=[self.kam.pk],
                    channels=[NotificationChannel.SYSTEM],
                    text="Вас назначили КАМом — МГУ",
                    kind=NotificationKind.ASSIGNMENT,
                    link="/interactions?interaction=1",
                ),
                call(
                    user_ids=[self.kam.pk],
                    channels=EXTERNAL,
                    text="СОВА: Вас назначили КАМом — МГУ",
                    kind=NotificationKind.ASSIGNMENT,
                    link="/interactions?interaction=1",
                ),
            ],
        )

    def test_only_enabled_channels(self, task) -> None:
        """Выключенные каналы не отправляются; группа без каналов не ставится."""
        self.set_rule(is_channel_telegram=False, is_channel_max=False, is_channel_system=False)

        self.notify(responsible=self.kam)

        # Проверяем одну постановку — только email
        self.assertEqual(task.delay.call_count, 1)
        self.assertEqual(task.delay.call_args.kwargs["channels"], [NotificationChannel.EMAIL])

    def test_head_flag_adds_head_without_duplicates(self, task) -> None:
        """Флаг руководителя добавляет его; один пользователь в обеих ролях получает одно уведомление."""
        self.set_rule(is_notify_head=True, is_channel_telegram=False, is_channel_max=False, is_channel_email=False)

        self.notify(responsible=self.kam, head=self.head)
        self.notify(responsible=self.kam, head=self.kam)

        # Проверяем получателей обоих вызовов
        self.assertEqual(
            [item.kwargs["user_ids"] for item in task.delay.call_args_list],
            [[self.kam.pk, self.head.pk], [self.kam.pk]],
        )

    def test_actor_and_inactive_are_skipped(self, task) -> None:
        """Инициатор события и неактивный пользователь не получают уведомление."""
        inactive = UserFactory(is_active=False)

        self.notify(responsible=self.kam, actor=self.kam)
        self.notify(responsible=inactive)

        # Проверяем, что задача не ставилась
        task.delay.assert_not_called()

    def test_disabled_type_sends_nothing(self, task) -> None:
        """Выключенный тип ничего не отправляет."""
        self.set_rule(is_enabled=False)

        self.notify(responsible=self.kam)

        # Проверяем, что задача не ставилась
        task.delay.assert_not_called()

    def test_missing_settings_row_logs_warning(self, task) -> None:
        """Нет строки настроек — предупреждение в лог, отправки нет."""
        NotifySettings.objects.filter(notify_type=NotifyType.KAM_ASSIGNED).delete()

        with self.assertLogs("django", level="WARNING") as logs:
            self.notify(responsible=self.kam)

        # Проверяем предупреждение
        self.assertIn("kam_assigned", logs.output[0])
        # Проверяем, что задача не ставилась
        task.delay.assert_not_called()

    def test_rolled_back_transaction_sends_nothing(self, task) -> None:
        """Откат транзакции события — задача не ставится."""
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            try:
                with transaction.atomic():
                    event_notification_service.notify(
                        notify_type=NotifyType.KAM_ASSIGNED,
                        message=self.message,
                        responsible=self.kam,
                    )
                    raise RuntimeError
            except RuntimeError:
                pass

        # Проверяем, что колбэков нет и задача не ставилась
        self.assertEqual(callbacks, [])
        task.delay.assert_not_called()


    def test_broker_failure_does_not_break_event(self, task) -> None:
        """Сбой брокера при постановке задачи логируется и не пробрасывается: событие уже зафиксировано."""
        task.delay.side_effect = ConnectionError("broker down")

        with self.assertLogs("django", level="ERROR") as logs:
            self.notify(responsible=self.kam)

        # Проверяем, что обе постановки попытались выполниться, несмотря на сбой первой
        self.assertEqual(task.delay.call_count, 2)
        # Проверяем, что сбой залогирован
        self.assertIn("broker down", logs.output[0])

class SendEventNotificationTaskTest(TestCase):
    """Celery-задача отправки событийного уведомления."""

    def test_sends_to_active_users(self) -> None:
        """Активному пользователю — письмо и уведомление в системе; возвращает число успешных отправок."""
        user = UserFactory()

        sent = send_event_notification(
            user_ids=[user.pk],
            channels=[NotificationChannel.EMAIL, NotificationChannel.SYSTEM],
            text="Вас назначили КАМом — МГУ",
            kind=NotificationKind.ASSIGNMENT,
            link="/interactions?interaction=1",
        )

        # Проверяем число успешных отправок
        self.assertEqual(sent, 2)
        # Проверяем письмо
        self.assertEqual([message.to for message in mail.outbox], [[user.email]])
        # Проверяем уведомление в системе
        notification = Notification.objects.get()
        self.assertEqual(notification.kind, NotificationKind.ASSIGNMENT)
        self.assertEqual(notification.link, "/interactions?interaction=1")

    def test_skips_user_deactivated_before_run(self) -> None:
        """Пользователь, деактивированный до выполнения задачи, уведомление не получает."""
        user = UserFactory(is_active=False)

        sent = send_event_notification(
            user_ids=[user.pk],
            channels=[NotificationChannel.EMAIL],
            text="Вас назначили КАМом — МГУ",
            kind=NotificationKind.ASSIGNMENT,
            link="",
        )

        # Проверяем, что ничего не отправлено
        self.assertEqual(sent, 0)
        self.assertEqual(mail.outbox, [])
