from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from sova.core.tests.factories import UserFactory
from sova.notifications.models import NotificationProfile
from sova.notifications.services import telegram_webhook
from sova.notifications.tests.factories import NotificationProfileFactory, TelegramLinkTokenFactory


def _start_message(chat_id: int, text: str, chat_type: str = "private") -> dict:
    return {"message": {"chat": {"id": chat_id, "type": chat_type}, "text": text}}


class TelegramWebhookHandleUpdateTest(TestCase):
    """`/start <токен>` из личного чата привязывает Telegram к пользователю СОВА."""

    def test_valid_token_links_profile(self) -> None:
        """Действующий токен создаёт профиль и записывает chat_id, погашая токен."""
        token = TelegramLinkTokenFactory()

        result = telegram_webhook.handle_update(_start_message(555, f"/start {token.id}"))

        self.assertTrue(result.handled)
        profile = NotificationProfile.objects.get(user=token.user)
        self.assertEqual(profile.telegram_chat_id, "555")
        token.refresh_from_db()
        self.assertIsNotNone(token.used_at)
        self.assertIn("подключён", result.reply_text)

    def test_valid_token_updates_existing_profile_without_touching_other_fields(self) -> None:
        """У пользователя уже есть профиль — привязка меняет только telegram_chat_id."""
        profile = NotificationProfileFactory(email="notify@example.com", max_chat_id="max-1", telegram_chat_id="")
        token = TelegramLinkTokenFactory(user=profile.user)

        telegram_webhook.handle_update(_start_message(777, f"/start {token.id}"))

        profile.refresh_from_db()
        self.assertEqual(profile.telegram_chat_id, "777")
        self.assertEqual(profile.email, "notify@example.com")
        self.assertEqual(profile.max_chat_id, "max-1")

    def test_expired_token_is_rejected(self) -> None:
        """Просроченный токен не привязывает Telegram и профиль не создаётся."""
        token = TelegramLinkTokenFactory(expires_at=timezone.now() - timedelta(minutes=1))

        result = telegram_webhook.handle_update(_start_message(555, f"/start {token.id}"))

        self.assertFalse(NotificationProfile.objects.filter(user=token.user).exists())
        self.assertIn("недействительна", result.reply_text)

    def test_reused_token_is_rejected(self) -> None:
        """Уже использованный токен нельзя применить повторно."""
        token = TelegramLinkTokenFactory()
        token.mark_used()

        result = telegram_webhook.handle_update(_start_message(555, f"/start {token.id}"))

        self.assertFalse(NotificationProfile.objects.filter(user=token.user).exists())
        self.assertIn("недействительна", result.reply_text)

    def test_unknown_token_is_rejected(self) -> None:
        """Мусор вместо токена (не UUID) не приводит к исключению."""
        user = UserFactory()

        result = telegram_webhook.handle_update(_start_message(555, "/start not-a-token"))

        self.assertFalse(NotificationProfile.objects.filter(user=user).exists())
        self.assertIn("недействительна", result.reply_text)

    def test_group_chat_is_ignored(self) -> None:
        """/start из группового чата не обрабатывается."""
        token = TelegramLinkTokenFactory()

        result = telegram_webhook.handle_update(_start_message(-100, f"/start {token.id}", chat_type="group"))

        self.assertFalse(result.handled)
        self.assertFalse(NotificationProfile.objects.filter(user=token.user).exists())

    def test_start_without_payload_replies_with_help(self) -> None:
        """/start без токена (пользователь просто открыл бота) не создаёт профиль, но отвечает подсказкой."""
        result = telegram_webhook.handle_update(_start_message(555, "/start"))

        self.assertTrue(result.handled)
        self.assertFalse(NotificationProfile.objects.exists())
        self.assertIn("СОВА", result.reply_text)

    def test_chat_already_linked_to_another_user_is_rejected(self) -> None:
        """Чат, уже привязанный к другому пользователю, не перепривязывается неявно."""
        NotificationProfileFactory(telegram_chat_id="555")
        token = TelegramLinkTokenFactory()

        result = telegram_webhook.handle_update(_start_message(555, f"/start {token.id}"))

        self.assertIn("другому", result.reply_text)
        self.assertFalse(NotificationProfile.objects.filter(user=token.user).exists())
        token.refresh_from_db()
        self.assertIsNone(token.used_at)

    def test_repeated_webhook_delivery_is_idempotent(self) -> None:
        """Telegram может повторить update — повторная обработка не должна ломать состояние."""
        token = TelegramLinkTokenFactory()
        payload = _start_message(555, f"/start {token.id}")

        first = telegram_webhook.handle_update(payload)
        second = telegram_webhook.handle_update(payload)

        self.assertIn("подключён", first.reply_text)
        self.assertIn("недействительна", second.reply_text)
        self.assertEqual(NotificationProfile.objects.filter(user=token.user).count(), 1)


class TelegramWebhookSendReplyTest(TestCase):
    """send_reply отправляет ответ только если он предусмотрен обработкой."""

    @patch("sova.notifications.services.telegram_webhook.TelegramChannelSender.send")
    def test_sends_reply_when_present(self, mock_send) -> None:
        """Есть reply_text и chat_id — сообщение отправляется через TelegramChannelSender."""
        result = telegram_webhook.WebhookResult(handled=True, reply_text="ok", chat_id="555")

        telegram_webhook.send_reply(result)

        mock_send.assert_called_once()
        self.assertEqual(mock_send.call_args.args[0], "555")

    @patch("sova.notifications.services.telegram_webhook.TelegramChannelSender.send")
    def test_skips_when_not_handled(self, mock_send) -> None:
        """Update не относился к привязке — отправлять нечего."""
        telegram_webhook.send_reply(telegram_webhook.WebhookResult(handled=False))

        mock_send.assert_not_called()
