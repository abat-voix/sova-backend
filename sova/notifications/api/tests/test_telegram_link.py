from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import SystemRole, UserRole
from sova.core.tests.factories import UserFactory
from sova.notifications.models import TelegramLinkToken
from sova.notifications.tests.factories import NotificationProfileFactory


class TelegramLinkApiTestCase(APITestCase):
    """Тесты /api/notifications/telegram/ — статус/ссылка привязки и отключение."""

    def setUp(self) -> None:
        self.user = UserFactory()
        UserRole.objects.create(user=self.user, role=SystemRole.KAM)
        self.client.force_authenticate(user=self.user)
        self.url = reverse("notifications:telegram-link")

    def test_get_requires_authentication(self) -> None:
        """Анонимный запрос отклоняется."""
        self.client.force_authenticate(user=None)

        response = self.client.get(self.url)

        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_get_returns_deep_link_when_not_connected(self) -> None:
        """Без привязанного Telegram отдаёт deep-ссылку и создаёт токен."""
        with self.settings(TELEGRAM_BOT_USERNAME="sova_bot"):
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["is_connected"])
        self.assertTrue(response.data["deep_link"].startswith("https://t.me/sova_bot?start="))
        self.assertEqual(TelegramLinkToken.objects.filter(user=self.user).count(), 1)

    def test_get_returns_connected_when_chat_id_set(self) -> None:
        """С привязанным chat_id отдаёт is_connected=True и без ссылки."""
        NotificationProfileFactory(user=self.user, telegram_chat_id="12345")

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["is_connected"])
        self.assertIsNone(response.data["deep_link"])

    def test_delete_disconnects_telegram(self) -> None:
        """DELETE очищает telegram_chat_id профиля текущего пользователя."""
        profile = NotificationProfileFactory(user=self.user, telegram_chat_id="12345")

        response = self.client.delete(self.url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        profile.refresh_from_db()
        self.assertEqual(profile.telegram_chat_id, "")

    def test_delete_requires_authentication(self) -> None:
        """Анонимный запрос на отключение отклоняется."""
        self.client.force_authenticate(user=None)

        response = self.client.delete(self.url)

        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))
