from rest_framework.test import APITestCase

from sova.core.tests.base import BaseApiTestMixin
from sova.core.tests.factories import UserFactory
from sova.notifications.models import NotificationProfile
from sova.notifications.tests.factories import NotificationProfileFactory


class NotificationProfileApiTestCase(BaseApiTestMixin, APITestCase):
    """Тесты CRUD /api/notifications/profiles/."""

    url_basename = "notifications:notification-profile"
    model = NotificationProfile

    def create_instance(self, **kwargs) -> NotificationProfile:
        """Создаёт профиль уведомлений."""
        return NotificationProfileFactory(**kwargs)

    def get_expected_data(self, instance: NotificationProfile) -> dict:
        """Поля read-представления профиля."""
        return {
            "id": str(instance.pk),
            "user": {
                "id": instance.user_id,
                "email": instance.user.email,
                "full_name": instance.user.get_full_name() or instance.user.get_username(),
            },
            "email": instance.email,
            "telegram_chat_id": instance.telegram_chat_id,
            "max_chat_id": instance.max_chat_id,
        }

    def get_post_data(self) -> dict:
        """Данные создания профиля (пользователь — по id)."""
        return {
            "user": UserFactory().pk,
            "email": "notify@example.com",
            "telegram_chat_id": "111",
            "max_chat_id": "222",
        }

    def get_change_data(self) -> dict:
        """Данные обновления профиля."""
        return {"telegram_chat_id": "999"}

    def get_search_term(self, instance: NotificationProfile) -> str:
        """Поиск по Telegram chat id."""
        return instance.telegram_chat_id

    def test_add_returns_400_for_second_profile_of_same_user(self) -> None:
        """Создание второго профиля для уже занятого пользователя возвращает 400."""
        profile = NotificationProfileFactory()

        response = self.client.post(
            path=self.list_url,
            data={"user": profile.user_id, "telegram_chat_id": "333"},
            format="json",
        )

        # Проверяем, что дубликат профиля отклонён валидацией
        self.assertEqual(response.status_code, 400)

    def test_filter_by_user(self) -> None:
        """Фильтр user возвращает профиль указанного пользователя."""
        target = NotificationProfileFactory()
        NotificationProfileFactory()

        response = self.client.get(path=self.list_url, data={"user": target.user_id})

        # Проверяем, что найден только профиль выбранного пользователя
        self.assertEqual(
            [item["id"] for item in response.data["results"]],
            [str(target.pk)],
        )
