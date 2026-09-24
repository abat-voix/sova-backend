from unittest.mock import Mock, patch

import requests
from django.core import mail
from django.test import SimpleTestCase, TestCase, override_settings

from sova.core.tests.factories import UserFactory
from sova.notifications.enum import NotificationKind
from sova.notifications.models import Notification
from sova.notifications.services.channels.email import EmailChannelSender
from sova.notifications.services.channels.max import MaxChannelSender
from sova.notifications.services.channels.system import SystemChannelSender
from sova.notifications.services.channels.telegram import TelegramChannelSender
from sova.notifications.services.message import Message


class EmailChannelSenderTest(TestCase):
    """Тесты EmailChannelSender.send()."""

    def test_send_delivers_message_with_subject_from_first_line(self) -> None:
        """send() отправляет письмо, тема — первая строка message."""
        sender = EmailChannelSender()

        result = sender.send(target="user@example.com", message=Message(text="Просрочен этап\nПодробности..."))

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

        result = sender.send(target="user@example.com", message=Message(text="Текст"))

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

        result = sender.send(target="123456", message=Message(text="Текст уведомления"))

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

        result = sender.send(target="123456", message=Message(text="Текст"))

        # Проверяем, что ошибка не поднимается наружу
        self.assertFalse(result)

    @patch("sova.notifications.services.channels.telegram.requests.post")
    def test_send_returns_false_on_http_error_status(self, post: Mock) -> None:
        """send() возвращает False, если Telegram API вернул код ошибки."""
        post.return_value = Mock(status_code=400)
        post.return_value.raise_for_status.side_effect = requests.HTTPError("400")
        sender = TelegramChannelSender()

        result = sender.send(target="123456", message=Message(text="Текст"))

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

        result = sender.send(target="789", message=Message(text="Текст уведомления"))

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

        result = sender.send(target="789", message=Message(text="Текст"))

        # Проверяем, что ошибка не поднимается наружу
        self.assertFalse(result)


class SystemChannelSenderTest(TestCase):
    """Тесты SystemChannelSender.send()."""

    def test_send_creates_notification_with_title_from_first_line(self) -> None:
        """send() создаёт уведомление: заголовок — первая строка, текст — остальное."""
        user = UserFactory()

        result = SystemChannelSender().send(target=user.pk, message=Message(text="Просрочен этап\n\nМГУ — B2B"))

        notification = Notification.objects.get()
        # Проверяем успешный результат
        self.assertTrue(result)
        # Проверяем получателя
        self.assertEqual(notification.recipient, user)
        # Проверяем заголовок
        self.assertEqual(notification.title, "Просрочен этап")
        # Проверяем текст без ведущих пустых строк
        self.assertEqual(notification.text, "МГУ — B2B")

    def test_send_single_line_message_has_empty_text(self) -> None:
        """Сообщение из одной строки — только заголовок, текст пустой."""
        user = UserFactory()

        SystemChannelSender().send(target=user.pk, message=Message(text="Просрочен этап"))

        # Проверяем пустой текст
        self.assertEqual(Notification.objects.get().text, "")

    def test_send_truncates_long_title(self) -> None:
        """Длинная первая строка обрезается до длины поля заголовка."""
        user = UserFactory()

        SystemChannelSender().send(target=user.pk, message=Message(text="А" * 300))

        # Проверяем длину заголовка
        self.assertEqual(len(Notification.objects.get().title), 255)

    @patch("sova.notifications.services.channels.system.Notification.objects.create", side_effect=RuntimeError("db"))
    def test_send_returns_false_on_error(self, create) -> None:
        """Ошибка записи не поднимается наружу — send() возвращает False."""
        result = SystemChannelSender().send(target=UserFactory().pk, message=Message(text="Текст"))

        # Проверяем неуспешный результат
        self.assertFalse(result)

    def test_send_stores_kind_and_link(self) -> None:
        """Группа и ссылка из Message сохраняются в уведомлении."""
        user = UserFactory()
        message = Message(text="Вам передано взаимодействие", kind=NotificationKind.ASSIGNMENT, link="/interactions/1")

        SystemChannelSender().send(target=user.pk, message=message)

        notification = Notification.objects.get()
        # Проверяем группу
        self.assertEqual(notification.kind, NotificationKind.ASSIGNMENT)
        # Проверяем ссылку
        self.assertEqual(notification.link, "/interactions/1")
