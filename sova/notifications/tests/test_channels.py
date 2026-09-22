from unittest.mock import Mock, patch

import requests
from django.core import mail
from django.test import SimpleTestCase, TestCase, override_settings

from sova.notifications.services.channels.email import EmailChannelSender
from sova.notifications.services.channels.max import MaxChannelSender
from sova.notifications.services.channels.telegram import TelegramChannelSender


class EmailChannelSenderTest(TestCase):
    """Тесты EmailChannelSender.send()."""

    def test_send_delivers_message_with_subject_from_first_line(self) -> None:
        """send() отправляет письмо, тема — первая строка message."""
        sender = EmailChannelSender()

        result = sender.send(target="user@example.com", message="Просрочен этап\nПодробности...")

        # Проверяем успешный результат
        self.assertTrue(result)
        # Проверяем, что письмо реально ушло через locmem-бэкенд тестов
        self.assertEqual(len(mail.outbox), 1)
        # Проверяем тему письма
        self.assertEqual(mail.outbox[0].subject, "Просрочен этап")
        # Проверяем получателя
        self.assertEqual(mail.outbox[0].to, ["user@example.com"])

    @patch("sova.notifications.services.channels.email.send_mail")
    def test_send_returns_false_on_backend_error(self, send_mail: Mock) -> None:
        """send() возвращает False и не поднимает исключение при ошибке бэкенда."""
        send_mail.side_effect = OSError("smtp unavailable")
        sender = EmailChannelSender()

        result = sender.send(target="user@example.com", message="Текст")

        # Проверяем, что ошибка не поднимается наружу
        self.assertFalse(result)


@override_settings(TELEGRAM_BOT_TOKEN="test-token", NOTIFICATION_HTTP_TIMEOUT=5)
class TelegramChannelSenderTest(SimpleTestCase):
    """Тесты TelegramChannelSender.send()."""

    @patch("sova.notifications.services.channels.telegram.requests.post")
    def test_send_posts_to_telegram_api(self, post: Mock) -> None:
        """send() отправляет POST на Telegram Bot API с chat_id и текстом."""
        post.return_value = Mock(status_code=200)
        sender = TelegramChannelSender()

        result = sender.send(target="123456", message="Текст уведомления")

        # Проверяем успешный результат
        self.assertTrue(result)
        # Проверяем URL с токеном бота
        self.assertEqual(post.call_args.args[0], "https://api.telegram.org/bottest-token/sendMessage")
        # Проверяем chat_id и текст в теле запроса
        self.assertEqual(post.call_args.kwargs["data"], {"chat_id": "123456", "text": "Текст уведомления"})
        # Проверяем таймаут запроса
        self.assertEqual(post.call_args.kwargs["timeout"], 5)

    @patch("sova.notifications.services.channels.telegram.requests.post")
    def test_send_returns_false_on_request_exception(self, post: Mock) -> None:
        """send() возвращает False, если Telegram API недоступен."""
        post.side_effect = requests.ConnectionError("connection refused")
        sender = TelegramChannelSender()

        result = sender.send(target="123456", message="Текст")

        # Проверяем, что ошибка не поднимается наружу
        self.assertFalse(result)

    @patch("sova.notifications.services.channels.telegram.requests.post")
    def test_send_returns_false_on_http_error_status(self, post: Mock) -> None:
        """send() возвращает False, если Telegram API вернул код ошибки."""
        post.return_value = Mock(status_code=400)
        post.return_value.raise_for_status.side_effect = requests.HTTPError("400")
        sender = TelegramChannelSender()

        result = sender.send(target="123456", message="Текст")

        # Проверяем, что HTTP-ошибка не поднимается наружу
        self.assertFalse(result)


@override_settings(
    MAX_BOT_TOKEN="test-max-token",
    MAX_API_URL="https://platform-api.max.ru",
    NOTIFICATION_HTTP_TIMEOUT=5,
)
class MaxChannelSenderTest(SimpleTestCase):
    """Тесты MaxChannelSender.send()."""

    @patch("sova.notifications.services.channels.max.requests.post")
    def test_send_posts_to_max_api(self, post: Mock) -> None:
        """send() отправляет POST на MAX Bot API с Bearer-токеном и chat_id в query."""
        post.return_value = Mock(status_code=200)
        sender = MaxChannelSender()

        result = sender.send(target="789", message="Текст уведомления")

        # Проверяем успешный результат
        self.assertTrue(result)
        # Проверяем URL
        self.assertEqual(post.call_args.args[0], "https://platform-api.max.ru/messages")
        # Проверяем chat_id в query-параметрах
        self.assertEqual(post.call_args.kwargs["params"], {"chat_id": "789"})
        # Проверяем текст сообщения в теле запроса
        self.assertEqual(post.call_args.kwargs["json"], {"text": "Текст уведомления"})
        # Проверяем заголовок авторизации
        self.assertEqual(post.call_args.kwargs["headers"], {"Authorization": "Bearer test-max-token"})

    @patch("sova.notifications.services.channels.max.requests.post")
    def test_send_returns_false_on_request_exception(self, post: Mock) -> None:
        """send() возвращает False, если MAX API недоступен."""
        post.side_effect = requests.ConnectionError("connection refused")
        sender = MaxChannelSender()

        result = sender.send(target="789", message="Текст")

        # Проверяем, что ошибка не поднимается наружу
        self.assertFalse(result)
