from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from sova.notifications.management.commands.telegram_poll_updates import Command


class TelegramPollUpdatesCommandTest(SimpleTestCase):
    @override_settings(
        TELEGRAM_BOT_TOKEN="test-token",
        TELEGRAM_PROXY="http://proxy.example:8888",
        NOTIFICATION_HTTP_TIMEOUT=10,
    )
    @patch("sova.notifications.management.commands.telegram_poll_updates.requests.get")
    def test_get_updates_uses_proxy_and_offset(self, get: Mock) -> None:
        get.return_value.json.return_value = {"ok": True, "result": []}

        updates = Command()._get_updates(offset=123)

        self.assertEqual(updates, [])
        self.assertEqual(get.call_args.kwargs["params"]["offset"], 123)
        self.assertEqual(
            get.call_args.kwargs["proxies"],
            {"http": "http://proxy.example:8888", "https": "http://proxy.example:8888"},
        )
