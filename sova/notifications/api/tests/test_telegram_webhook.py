import json
from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from sova.notifications.models import NotificationProfile
from sova.notifications.tests.factories import TelegramLinkTokenFactory


@override_settings(TELEGRAM_WEBHOOK_SECRET="whsecret")
class TelegramWebhookApiTestCase(APITestCase):
    """Тесты /api/notifications/telegram/webhook/ — приём update'ов Telegram."""

    def setUp(self) -> None:
        self.url = reverse("notifications:telegram-webhook")

    def _post(self, payload: dict, secret: str | None = "whsecret"):
        headers = {}
        if secret is not None:
            headers["X-Telegram-Bot-Api-Secret-Token"] = secret
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
            **{f"HTTP_{k.upper().replace('-', '_')}": v for k, v in headers.items()},
        )

    @patch("sova.notifications.api.views.telegram_webhook.telegram_webhook.send_reply")
    def test_valid_token_links_profile_and_returns_200(self, mock_send_reply) -> None:
        """Верный секрет и действующий токен привязывают Telegram, ответ 200."""
        token = TelegramLinkTokenFactory()
        payload = {"message": {"chat": {"id": 555, "type": "private"}, "text": f"/start {token.id}"}}

        response = self._post(payload)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(NotificationProfile.objects.get(user=token.user).telegram_chat_id, "555")
        mock_send_reply.assert_called_once()

    def test_missing_secret_is_rejected(self) -> None:
        """Запрос без заголовка секрета отклоняется."""
        response = self._post({"message": {}}, secret=None)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_wrong_secret_is_rejected(self) -> None:
        """Неверный секрет отклоняется."""
        response = self._post({"message": {}}, secret="wrong")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_invalid_json_returns_400(self) -> None:
        """Некорректный JSON в теле запроса — 400."""
        response = self.client.post(
            self.url,
            data="not-json",
            content_type="application/json",
            HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="whsecret",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unrelated_update_returns_200_without_side_effects(self) -> None:
        """Update без /start (например, произвольный текст) обрабатывается без ошибок."""
        response = self._post({"message": {"chat": {"id": 555, "type": "private"}, "text": "привет"}})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(NotificationProfile.objects.exists())
