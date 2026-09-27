from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from sova.notifications.models import NotificationProfile
from sova.notifications.services import telegram_bot
from sova.notifications.tests.factories import NotificationProfileFactory, TelegramLinkTokenFactory


def _start_message(chat_id: int, text: str, chat_type: str = "private") -> dict:
    return {"message": {"chat": {"id": chat_id, "type": chat_type}, "text": text}}


class TelegramBotHandleUpdateTest(TestCase):
    def test_valid_token_links_profile(self) -> None:
        token = TelegramLinkTokenFactory()

        result = telegram_bot.handle_update(_start_message(555, f"/start {token.id}"))

        self.assertTrue(result.handled)
        self.assertEqual(NotificationProfile.objects.get(user=token.user).telegram_chat_id, "555")
        token.refresh_from_db()
        self.assertIsNotNone(token.used_at)
        self.assertIn("подключён", result.reply_text)

    def test_expired_token_is_rejected(self) -> None:
        token = TelegramLinkTokenFactory(expires_at=timezone.now() - timedelta(minutes=1))

        result = telegram_bot.handle_update(_start_message(555, f"/start {token.id}"))

        self.assertFalse(NotificationProfile.objects.filter(user=token.user).exists())
        self.assertIn("недействительна", result.reply_text)

    def test_chat_already_linked_to_another_user_is_rejected(self) -> None:
        NotificationProfileFactory(telegram_chat_id="555")
        token = TelegramLinkTokenFactory()

        result = telegram_bot.handle_update(_start_message(555, f"/start {token.id}"))

        self.assertIn("другому", result.reply_text)
        self.assertFalse(NotificationProfile.objects.filter(user=token.user).exists())

    def test_group_chat_is_ignored(self) -> None:
        token = TelegramLinkTokenFactory()

        result = telegram_bot.handle_update(_start_message(-100, f"/start {token.id}", "group"))

        self.assertFalse(result.handled)
        self.assertFalse(NotificationProfile.objects.filter(user=token.user).exists())

    @patch("sova.notifications.services.telegram_bot.TelegramChannelSender.send", return_value=True)
    def test_reply_uses_telegram_sender(self, send) -> None:
        result = telegram_bot.BotUpdateResult(handled=True, reply_text="ok", chat_id="555")

        self.assertTrue(telegram_bot.send_reply(result))
        send.assert_called_once()
