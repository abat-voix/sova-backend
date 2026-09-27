from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from sova.core.tests.factories import UserFactory
from sova.notifications.models import NotificationProfile, TelegramLinkToken
from sova.notifications.services import telegram_link
from sova.notifications.tests.factories import NotificationProfileFactory, TelegramLinkTokenFactory


@override_settings(TELEGRAM_BOT_USERNAME="sova_bot", TELEGRAM_LINK_TOKEN_TTL_MINUTES=30)
class TelegramLinkServiceTest(TestCase):
    """Выпуск токена/ссылки привязки и отключение Telegram."""

    def test_issue_link_token_sets_expiry_from_settings(self) -> None:
        """Токен получает срок действия из TELEGRAM_LINK_TOKEN_TTL_MINUTES."""
        user = UserFactory()

        token = telegram_link.issue_link_token(user)

        # Проверяем, что срок действия близок к now()+30 минут
        expected = timezone.now() + timedelta(minutes=30)
        self.assertAlmostEqual(token.expires_at, expected, delta=timedelta(seconds=5))
        self.assertIsNone(token.used_at)

    def test_build_deep_link_uses_bot_username_and_token_id(self) -> None:
        """Deep-ссылка содержит имя бота и id токена как payload /start."""
        token = TelegramLinkTokenFactory()

        link = telegram_link.build_deep_link(token)

        self.assertEqual(link, f"https://t.me/sova_bot?start={token.id}")

    @override_settings(TELEGRAM_BOT_USERNAME="")
    def test_build_deep_link_returns_none_without_bot_username(self) -> None:
        """Без настроенного имени бота ссылку строить нельзя."""
        token = TelegramLinkTokenFactory()

        self.assertIsNone(telegram_link.build_deep_link(token))

    def test_get_link_status_not_connected_creates_token(self) -> None:
        """Без привязанного chat_id статус not-connected и есть ссылка на бота."""
        user = UserFactory()

        status = telegram_link.get_link_status(user)

        self.assertFalse(status.is_connected)
        self.assertIsNotNone(status.deep_link)
        self.assertEqual(TelegramLinkToken.objects.filter(user=user).count(), 1)

    def test_get_link_status_reuses_valid_pending_token(self) -> None:
        """Повторный запрос статуса не создаёт новый токен, пока действующий не погашен."""
        user = UserFactory()
        first = telegram_link.get_link_status(user)

        second = telegram_link.get_link_status(user)

        self.assertEqual(first.deep_link, second.deep_link)
        self.assertEqual(TelegramLinkToken.objects.filter(user=user).count(), 1)

    def test_get_link_status_connected_when_chat_id_set(self) -> None:
        """Если в профиле уже есть telegram_chat_id — статус connected, ссылки нет."""
        profile = NotificationProfileFactory(telegram_chat_id="12345")

        status = telegram_link.get_link_status(profile.user)

        self.assertTrue(status.is_connected)
        self.assertIsNone(status.deep_link)

    def test_disconnect_clears_chat_id(self) -> None:
        """Отключение очищает telegram_chat_id, не трогая остальные поля профиля."""
        profile = NotificationProfileFactory(telegram_chat_id="12345", email="notify@example.com")

        telegram_link.disconnect(profile.user)

        profile.refresh_from_db()
        self.assertEqual(profile.telegram_chat_id, "")
        self.assertEqual(profile.email, "notify@example.com")

    def test_disconnect_without_profile_does_nothing(self) -> None:
        """У пользователя без профиля отключение не создаёт профиль и не падает."""
        user = UserFactory()

        telegram_link.disconnect(user)

        self.assertFalse(NotificationProfile.objects.filter(user=user).exists())
