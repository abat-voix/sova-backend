from django.db import IntegrityError
from django.test import TestCase

from sova.notifications.enum import NotificationKind
from sova.notifications.models import Notification
from sova.notifications.tests.factories import NotificationFactory, NotificationProfileFactory


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


class NotificationModelTest(TestCase):
    """Тесты модели Notification."""

    def test_str_returns_title(self) -> None:
        """__str__ возвращает заголовок уведомления."""
        notification = NotificationFactory(title="Просрочен этап")

        # Проверяем строковое представление
        self.assertEqual(str(notification), "Просрочен этап")

    def test_new_notification_is_unread(self) -> None:
        """Новое уведомление по умолчанию не прочитано."""
        notification = NotificationFactory()

        # Проверяем флаг прочтения
        self.assertFalse(notification.is_read)

    def test_default_kind_is_system(self) -> None:
        """Группа по умолчанию — системные, ссылка пустая."""
        notification = Notification.objects.create(recipient=NotificationFactory().recipient, title="Заголовок")

        # Проверяем группу и ссылку
        self.assertEqual(notification.kind, NotificationKind.SYSTEM)
        self.assertEqual(notification.link, "")

    def test_default_ordering_is_newest_first(self) -> None:
        """Уведомления по умолчанию упорядочены от новых к старым."""
        older = NotificationFactory()
        newer = NotificationFactory()

        # Проверяем порядок выборки
        self.assertEqual(list(Notification.objects.all()), [newer, older])
