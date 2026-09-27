from unittest.mock import Mock, patch

from django.core.management import call_command
from django.test import SimpleTestCase, override_settings


class TelegramSetWebhookCommandTestCase(SimpleTestCase):
    @override_settings(
        TELEGRAM_BOT_TOKEN="test-token",
        TELEGRAM_WEBHOOK_SECRET="test-secret",
        TELEGRAM_PROXY="http://proxy.example:8888",
        NOTIFICATION_HTTP_TIMEOUT=10,
    )
    @patch("sova.notifications.management.commands.telegram_set_webhook.requests.post")
    def test_set_webhook_uses_telegram_proxy(self, post: Mock) -> None:
        post.return_value.json.return_value = {"ok": True}

        call_command("telegram_set_webhook", base_url="https://dev.sova.1uup.ru")

        self.assertEqual(
            post.call_args.kwargs["proxies"],
            {"http": "http://proxy.example:8888", "https": "http://proxy.example:8888"},
        )
