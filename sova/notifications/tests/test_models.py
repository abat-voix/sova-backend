from django.db import IntegrityError
from django.test import TestCase

from sova.notifications.tests.factories import NotificationProfileFactory


class NotificationProfileModelTest(TestCase):
    """Тесты модели NotificationProfile."""

    def test_str_returns_user(self) -> None:
        """__str__ возвращает строковое представление пользователя."""
        profile = NotificationProfileFactory()

        result = str(profile)

        # Проверяем, что строковое представление совпадает с пользователем
        self.assertEqual(result, str(profile.user))

    def test_create_second_profile_for_same_user_raises_integrity_error(self) -> None:
        """Повторное создание профиля для уже занятого пользователя нарушает уникальность OneToOne."""
        profile = NotificationProfileFactory()

        # Проверяем, что второй профиль для того же пользователя создать нельзя
        with self.assertRaises(IntegrityError):
            NotificationProfileFactory(user=profile.user)
