from unittest.mock import patch

from django.test import TestCase

from sova.core.tests.factories import UserFactory
from sova.notifications.enum import NotificationChannel
from sova.notifications.services.notifier import NotificationService
from sova.notifications.services.recipient import Recipient
from sova.notifications.tests.factories import NotificationProfileFactory


class NotificationServiceSendTest(TestCase):
    """Тесты NotificationService.send()."""

    def test_send_to_user_without_profile_only_sends_email(self) -> None:
        """send() пользователю без NotificationProfile отправляет только email, минуя telegram/max."""
        user = UserFactory()
        service = NotificationService()

        with (
            patch.object(service._senders[NotificationChannel.EMAIL], "send", return_value=True) as email_send,
            patch.object(service._senders[NotificationChannel.TELEGRAM], "send") as telegram_send,
            patch.object(service._senders[NotificationChannel.MAX], "send") as max_send,
        ):
            results = service.send(recipient=user, message="Текст")

        # Проверяем, что отправка была только по email
        self.assertEqual([result.channel for result in results], [NotificationChannel.EMAIL])
        # Проверяем, что результат успешен
        self.assertTrue(results[0].success)
        # Проверяем, что email реально вызван с адресом пользователя
        email_send.assert_called_once_with(target=user.email, message="Текст")
        # Проверяем, что telegram и max не вызывались — адресов нет
        telegram_send.assert_not_called()
        max_send.assert_not_called()

    def test_send_to_multiple_recipients_covers_each(self) -> None:
        """send() со списком получателей отправляет каждому по всем доступным каналам."""
        first_profile = NotificationProfileFactory(telegram_chat_id="111", max_chat_id="")
        second_profile = NotificationProfileFactory(telegram_chat_id="222", max_chat_id="")
        service = NotificationService()

        with (
            patch.object(service._senders[NotificationChannel.EMAIL], "send", return_value=True),
            patch.object(service._senders[NotificationChannel.TELEGRAM], "send", return_value=True) as telegram_send,
            patch.object(service._senders[NotificationChannel.MAX], "send") as max_send,
        ):
            results = service.send(recipient=[first_profile.user, second_profile.user], message="Текст")

        # Проверяем, что telegram вызван для обоих получателей
        self.assertEqual(telegram_send.call_count, 2)
        # Проверяем, что max не вызывался — у обоих получателей пустой max_chat_id
        max_send.assert_not_called()
        # Проверяем общее число результатов: 2 канала (email+telegram) на каждого из двух получателей
        self.assertEqual(len(results), 4)

    def test_send_with_channels_filter_uses_only_requested_channels(self) -> None:
        """send() с channels=[...] отправляет только по указанным каналам."""
        recipient = Recipient(email="user@example.com", telegram_chat_id="123", max_chat_id="456")
        service = NotificationService()

        with (
            patch.object(service._senders[NotificationChannel.EMAIL], "send", return_value=True) as email_send,
            patch.object(service._senders[NotificationChannel.TELEGRAM], "send") as telegram_send,
            patch.object(service._senders[NotificationChannel.MAX], "send") as max_send,
        ):
            service.send(recipient=recipient, message="Текст", channels=[NotificationChannel.EMAIL])

        # Проверяем, что вызван только email
        email_send.assert_called_once()
        # Проверяем, что telegram и max не вызывались — не запрошены
        telegram_send.assert_not_called()
        max_send.assert_not_called()

    def test_send_isolates_channel_error_from_other_channels(self) -> None:
        """send() продолжает отправку по остальным каналам, если один канал упал с исключением."""
        recipient = Recipient(email="user@example.com", telegram_chat_id="123", max_chat_id="456")
        service = NotificationService()

        with (
            patch.object(service._senders[NotificationChannel.EMAIL], "send", side_effect=RuntimeError("boom")),
            patch.object(service._senders[NotificationChannel.TELEGRAM], "send", return_value=True),
            patch.object(service._senders[NotificationChannel.MAX], "send", return_value=True),
        ):
            results = service.send(recipient=recipient, message="Текст")

        results_by_channel = {result.channel: result.success for result in results}
        # Проверяем, что упавший канал вернулся в результатах как неуспешный
        self.assertFalse(results_by_channel[NotificationChannel.EMAIL])
        # Проверяем, что остальные каналы всё равно отработали успешно
        self.assertTrue(results_by_channel[NotificationChannel.TELEGRAM])
        # Проверяем, что остальные каналы всё равно отработали успешно
        self.assertTrue(results_by_channel[NotificationChannel.MAX])

    def test_send_to_recipient_without_addresses_returns_empty_list(self) -> None:
        """send() получателю без единого адреса возвращает пустой список без исключений."""
        recipient = Recipient()
        service = NotificationService()

        results = service.send(recipient=recipient, message="Текст")

        # Проверяем, что результатов нет и исключение не поднято
        self.assertEqual(results, [])
