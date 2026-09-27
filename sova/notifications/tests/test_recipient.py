from django.test import TestCase

from sova.core.tests.factories import UserFactory
from sova.notifications.services.recipient import Recipient
from sova.notifications.tests.factories import NotificationProfileFactory


class RecipientForUserTest(TestCase):
    """Тесты Recipient.for_user()."""

    def test_for_user_returns_all_addresses_with_profile(self) -> None:
        """for_user() с заполненным профилем возвращает email, telegram и max адреса."""
        profile = NotificationProfileFactory(telegram_chat_id="123", max_chat_id="456")

        recipient = Recipient.for_user(profile.user)

        # Проверяем email пользователя
        self.assertEqual(recipient.email, profile.user.email)
        # Проверяем telegram_chat_id из профиля
        self.assertEqual(recipient.telegram_chat_id, "123")
        # Проверяем max_chat_id из профиля
        self.assertEqual(recipient.max_chat_id, "456")

    def test_for_user_sets_user_id(self) -> None:
        """for_user() сохраняет id пользователя — адрес системного канала."""
        user = UserFactory()

        recipient = Recipient.for_user(user)

        # Проверяем id пользователя
        self.assertEqual(recipient.user_id, user.pk)

    def test_manual_recipient_has_no_user_id(self) -> None:
        """Recipient, собранный вручную, без user_id — системный канал ему не шлётся."""
        recipient = Recipient(email="user@example.com")

        # Проверяем отсутствие id пользователя
        self.assertIsNone(recipient.user_id)

    def test_for_user_without_profile_returns_only_email(self) -> None:
        """for_user() без NotificationProfile возвращает telegram_chat_id/max_chat_id равными None."""
        user = UserFactory()

        recipient = Recipient.for_user(user)

        # Проверяем, что email взят из пользователя
        self.assertEqual(recipient.email, user.email)
        # Проверяем отсутствие telegram-адреса
        self.assertIsNone(recipient.telegram_chat_id)
        # Проверяем отсутствие max-адреса
        self.assertIsNone(recipient.max_chat_id)

    def test_for_user_with_blank_profile_fields_returns_none(self) -> None:
        """for_user() с пустыми полями профиля возвращает None, а не пустую строку."""
        profile = NotificationProfileFactory(telegram_chat_id="", max_chat_id="")

        recipient = Recipient.for_user(profile.user)

        # Проверяем, что пустой telegram_chat_id преобразуется в None
        self.assertIsNone(recipient.telegram_chat_id)
        # Проверяем, что пустой max_chat_id преобразуется в None
        self.assertIsNone(recipient.max_chat_id)

    def test_for_user_without_email_returns_none(self) -> None:
        """for_user() у пользователя без email возвращает email равным None."""
        user = UserFactory(email="")

        recipient = Recipient.for_user(user)

        # Проверяем, что пустой email преобразуется в None
        self.assertIsNone(recipient.email)

    def test_for_user_prefers_profile_email_over_user_email(self) -> None:
        """for_user() при заполненном profile.email использует его вместо user.email."""
        profile = NotificationProfileFactory(email="notify@example.com")

        recipient = Recipient.for_user(profile.user)

        # Проверяем, что взят email из профиля
        self.assertEqual(recipient.email, "notify@example.com")
        # Проверяем, что email пользователя не используется
        self.assertNotEqual(recipient.email, profile.user.email)
