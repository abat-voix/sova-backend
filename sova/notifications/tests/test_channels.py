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

    @override_settings(FRONTEND_URL="https://sova.example.ru")
    def test_send_appends_absolute_link_to_body(self) -> None:
        """Ссылка из Message дописывается в конец письма полным адресом; тема не меняется."""
        EmailChannelSender().send(
            target="user@example.com",
            message=Message(text="Вас назначили КАМом\nМГУ", link="/interactions?interaction=1"),
        )

        # Проверяем тело письма
        self.assertEqual(mail.outbox[0].body, "Вас назначили КАМом\nМГУ\n\nhttps://sova.example.ru/interactions?interaction=1")
        # Проверяем, что тема — по-прежнему первая строка
        self.assertEqual(mail.outbox[0].subject, "Вас назначили КАМом")

    @override_settings(FRONTEND_URL="")
    def test_send_without_frontend_url_skips_link(self) -> None:
        """Без FRONTEND_URL письмо уходит без ссылки — относительный адрес наружу не попадает."""
        EmailChannelSender().send(
            target="user@example.com",
            message=Message(text="Вас назначили КАМом", link="/interactions?interaction=1"),
        )

        # Проверяем тело письма
        self.assertEqual(mail.outbox[0].body, "Вас назначили КАМом")


@override_settings(TELEGRAM_BOT_TOKEN="test-token", TELEGRAM_PROXY="", NOTIFICATION_HTTP_TIMEOUT=5)
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
        # Без TELEGRAM_PROXY запрос не получает proxy-настройки
        self.assertNotIn("proxies", post.call_args.kwargs)

    @override_settings(TELEGRAM_PROXY="socks5h://proxy-user:proxy-pass@127.0.0.1:1080")
    @patch("sova.notifications.services.channels.telegram.requests.post")
    def test_send_uses_configured_proxy(self, post: Mock) -> None:
        """TELEGRAM_PROXY применяется к HTTP- и HTTPS-запросам Telegram sender."""
        post.return_value = Mock(status_code=200)
        sender = TelegramChannelSender()

        result = sender.send(target="123456", message=Message(text="Текст уведомления"))

        self.assertTrue(result)
        self.assertEqual(
            post.call_args.kwargs["proxies"],
            {
                "http": "socks5h://proxy-user:proxy-pass@127.0.0.1:1080",
                "https": "socks5h://proxy-user:proxy-pass@127.0.0.1:1080",
            },
        )

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

    @override_settings(TELEGRAM_BOT_TOKEN="")
    @patch("sova.notifications.services.channels.telegram.requests.post")
    def test_send_without_token_skips_request_and_warns_once(self, post: Mock) -> None:
        """Без токена send() возвращает False без запроса и предупреждает в лог один раз."""
        sender = TelegramChannelSender()

        with self.assertLogs("django", level="WARNING") as logs:
            first = sender.send(target="123456", message=Message(text="Текст"))
            second = sender.send(target="654321", message=Message(text="Текст"))

        # Проверяем неуспешный результат обеих отправок
        self.assertFalse(first)
        self.assertFalse(second)
        # Проверяем, что запрос к Telegram API не выполнялся
        post.assert_not_called()
        # Проверяем, что предупреждение записано один раз
        self.assertEqual(len(logs.records), 1)

    @override_settings(FRONTEND_URL="https://sova.example.ru")
    @patch("sova.notifications.services.channels.telegram.requests.post")
    def test_send_appends_absolute_link(self, post: Mock) -> None:
        """Ссылка из Message дописывается в конец текста полным адресом."""
        post.return_value = Mock(status_code=200)

        TelegramChannelSender().send(target="123456", message=Message(text="Текст", link="/interactions?interaction=1"))

        # Проверяем текст со ссылкой
        self.assertEqual(
            post.call_args.kwargs["data"]["text"],
            "Текст\n\nhttps://sova.example.ru/interactions?interaction=1",
        )

    @patch("sova.notifications.services.channels.telegram.TELEGRAM_MESSAGE_MAX_LENGTH", 21)
    @patch("sova.notifications.services.channels.telegram.requests.post")
    def test_send_splits_long_text_by_lines(self, post: Mock) -> None:
        """Текст длиннее лимита уходит несколькими сообщениями по границам строк."""
        post.return_value = Mock(status_code=200)

        result = TelegramChannelSender().send(target="123456", message=Message(text="Строка один\nСтрока два\nСтрока три"))

        # Проверяем успешный результат
        self.assertTrue(result)
        # Проверяем части: каждая не длиннее лимита, строки не разорваны
        self.assertEqual(
            [call.kwargs["data"]["text"] for call in post.call_args_list],
            ["Строка один", "Строка два\nСтрока три"],
        )

    @patch("sova.notifications.services.channels.telegram.TELEGRAM_MESSAGE_MAX_LENGTH", 21)
    @patch("sova.notifications.services.channels.telegram.requests.post")
    def test_send_fails_if_any_part_fails(self, post: Mock) -> None:
        """Если не дошла одна из частей, отправка неуспешна — сводка повторится на следующем запуске."""
        failed = Mock(status_code=400)
        failed.raise_for_status.side_effect = requests.HTTPError("400")
        post.side_effect = [Mock(status_code=200), failed]

        result = TelegramChannelSender().send(target="123456", message=Message(text="Строка один\nСтрока два\nСтрока три"))

        # Проверяем неуспешный результат
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

    @override_settings(MAX_BOT_TOKEN="")
    @patch("sova.notifications.services.channels.max.requests.post")
    def test_send_without_token_skips_request_and_warns_once(self, post: Mock) -> None:
        """Без токена send() возвращает False без запроса и предупреждает в лог один раз."""
        sender = MaxChannelSender()

        with self.assertLogs("django", level="WARNING") as logs:
            first = sender.send(target="789", message=Message(text="Текст"))
            second = sender.send(target="987", message=Message(text="Текст"))

        # Проверяем неуспешный результат обеих отправок
        self.assertFalse(first)
        self.assertFalse(second)
        # Проверяем, что запрос к MAX API не выполнялся
        post.assert_not_called()
        # Проверяем, что предупреждение записано один раз
        self.assertEqual(len(logs.records), 1)


    @override_settings(FRONTEND_URL="https://sova.example.ru")
    @patch("sova.notifications.services.channels.max.requests.post")
    def test_send_appends_absolute_link(self, post: Mock) -> None:
        """Ссылка из Message дописывается в конец текста полным адресом."""
        post.return_value = Mock(status_code=200)

        MaxChannelSender().send(target="789", message=Message(text="Текст", link="/interactions?interaction=1"))

        # Проверяем текст со ссылкой
        self.assertEqual(
            post.call_args.kwargs["json"],
            {"text": "Текст\n\nhttps://sova.example.ru/interactions?interaction=1"},
        )

    @patch("sova.notifications.services.channels.max.MAX_MESSAGE_MAX_LENGTH", 21)
    @patch("sova.notifications.services.channels.max.requests.post")
    def test_send_splits_long_text_by_lines(self, post: Mock) -> None:
        """Текст длиннее лимита уходит несколькими сообщениями по границам строк."""
        post.return_value = Mock(status_code=200)

        MaxChannelSender().send(target="789", message=Message(text="Строка один\nСтрока два\nСтрока три"))

        # Проверяем части
        self.assertEqual(
            [call.kwargs["json"]["text"] for call in post.call_args_list],
            ["Строка один", "Строка два\nСтрока три"],
        )


class ChunksTest(SimpleTestCase):
    """Разбиение длинного текста на части для мессенджеров."""

    def test_short_text_is_single_chunk(self) -> None:
        """Текст в пределах лимита — одна часть без изменений."""
        # Проверяем одну часть
        self.assertEqual(TelegramChannelSender()._chunks("А\n\nБ", limit=10), ["А\n\nБ"])

    def test_long_line_is_cut_by_limit(self) -> None:
        """Строка длиннее лимита режется на куски по лимиту."""
        # Проверяем нарезку
        self.assertEqual(TelegramChannelSender()._chunks("Тема\n" + "х" * 12, limit=5), ["Тема", "ххххх", "ххххх", "хх"])

    def test_blank_lines_on_chunk_border_are_dropped(self) -> None:
        """Пустые строки на границе частей не дают пустых сообщений."""
        # Проверяем, что части не начинаются и не заканчиваются пустой строкой
        self.assertEqual(TelegramChannelSender()._chunks("Тема\n\nПункт один", limit=10), ["Тема", "Пункт один"])


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

    @override_settings(FRONTEND_URL="https://sova.example.ru")
    def test_send_keeps_relative_link_and_text(self) -> None:
        """Колокольчик хранит относительную ссылку и не дописывает её в текст — фронт переходит сам."""
        user = UserFactory()

        SystemChannelSender().send(target=user.pk, message=Message(text="Заголовок\nТекст", link="/interactions/1"))

        notification = Notification.objects.get()
        # Проверяем относительную ссылку
        self.assertEqual(notification.link, "/interactions/1")
        # Проверяем текст без ссылки
        self.assertEqual(notification.text, "Текст")
