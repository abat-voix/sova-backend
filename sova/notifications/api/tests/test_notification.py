from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import SystemRole, UserRole
from sova.core.tests.factories import UserFactory
from sova.notifications.enum import NotificationKind
from sova.notifications.models import Notification
from sova.notifications.tests.factories import NotificationFactory


class NotificationInboxApiTestCase(APITestCase):
    """Тесты /api/notifications/inbox/: только свои уведомления, счётчик и прочтение."""

    def setUp(self) -> None:
        """Пользователь с двумя уведомлениями и чужое уведомление."""
        self.user = UserFactory()
        UserRole.objects.create(user=self.user, role=SystemRole.KAM)
        self.client.force_authenticate(user=self.user)
        self.read = NotificationFactory(recipient=self.user, is_read=True)
        self.unread = NotificationFactory(recipient=self.user)
        self.foreign = NotificationFactory()

    def url(self, name: str, **kwargs) -> str:
        """URL эндпоинта по имени роутера."""
        return reverse(f"notifications:notification-inbox-{name}", kwargs=kwargs)

    def test_list_returns_only_own_newest_first(self) -> None:
        """Список — только уведомления текущего пользователя, новые сверху."""
        response = self.client.get(self.url("list"))

        # Проверяем статус
        self.assertEqual(response.status_code, 200)
        # Проверяем состав и порядок
        self.assertEqual([item["id"] for item in response.data["results"]], [str(self.unread.pk), str(self.read.pk)])

    def test_list_item_fields(self) -> None:
        """Поля уведомления в списке."""
        response = self.client.get(self.url("list"), data={"is_read": "false"})

        # Проверяем представление
        self.assertEqual(
            response.data["results"],
            [
                {
                    "id": str(self.unread.pk),
                    "title": self.unread.title,
                    "text": self.unread.text,
                    "is_read": False,
                    "kind": NotificationKind.SYSTEM,
                    "kind_label": "Системные",
                    "link": "",
                    "created_at": response.data["results"][0]["created_at"],
                },
            ],
        )

    def test_retrieve_foreign_returns_404(self) -> None:
        """Чужое уведомление не найдено."""
        response = self.client.get(self.url("detail", pk=self.foreign.pk))

        # Проверяем, что чужое уведомление скрыто
        self.assertEqual(response.status_code, 404)

    def test_unread_count(self) -> None:
        """Счётчик непрочитанных — только свои."""
        response = self.client.get(self.url("unread-count"))

        # Проверяем счётчик
        self.assertEqual(response.data, {"count": 1})

    def test_read_marks_notification(self) -> None:
        """POST read отмечает уведомление прочитанным и возвращает его."""
        response = self.client.post(self.url("read", pk=self.unread.pk))

        self.unread.refresh_from_db()
        # Проверяем статус и флаг в ответе
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["is_read"])
        # Проверяем флаг в БД
        self.assertTrue(self.unread.is_read)

    def test_read_foreign_returns_404(self) -> None:
        """Чужое уведомление прочитать нельзя."""
        response = self.client.post(self.url("read", pk=self.foreign.pk))

        self.foreign.refresh_from_db()
        # Проверяем статус и что флаг не изменился
        self.assertEqual(response.status_code, 404)
        self.assertFalse(self.foreign.is_read)

    def test_read_all_marks_only_own(self) -> None:
        """read-all отмечает только свои непрочитанные."""
        response = self.client.post(self.url("read-all"))

        # Проверяем число отмеченных
        self.assertEqual(response.data, {"updated": 1})
        # Проверяем, что чужое уведомление не тронуто
        self.assertFalse(Notification.objects.get(pk=self.foreign.pk).is_read)

    def test_create_and_delete_are_not_allowed(self) -> None:
        """Создавать и удалять уведомления через API нельзя."""
        create = self.client.post(self.url("list"), data={"title": "x"})
        delete = self.client.delete(self.url("detail", pk=self.unread.pk))

        # Проверяем, что методы не разрешены
        self.assertEqual(create.status_code, 405)
        self.assertEqual(delete.status_code, 405)

    def test_anonymous_is_denied(self) -> None:
        """Без аутентификации доступа нет."""
        self.client.force_authenticate(user=None)

        response = self.client.get(self.url("unread-count"))

        # Проверяем отказ
        self.assertIn(response.status_code, (401, 403))

    def test_filter_by_kind(self) -> None:
        """Фильтр kind возвращает только уведомления этой группы."""
        deadline = NotificationFactory(recipient=self.user, kind=NotificationKind.DEADLINE)

        response = self.client.get(self.url("list"), data={"kind": NotificationKind.DEADLINE})

        # Проверяем состав
        self.assertEqual([item["id"] for item in response.data["results"]], [str(deadline.pk)])

    def test_kinds_lists_all_groups_with_own_counts(self) -> None:
        """kinds — все группы в порядке enum, с числом своих уведомлений и непрочитанных, включая пустые."""
        NotificationFactory(recipient=self.user, kind=NotificationKind.DEADLINE)
        NotificationFactory(kind=NotificationKind.DEADLINE)

        response = self.client.get(self.url("kinds"))

        # Проверяем группы, подписи, иконки и счётчики текущего пользователя
        self.assertEqual(
            response.data,
            [
                {"value": "deadline", "label": "Сроки", "icon": "calendar-clock", "count": 1, "unread_count": 1},
                {"value": "assignment", "label": "Назначения", "icon": "user-check", "count": 0, "unread_count": 0},
                {"value": "system", "label": "Системные", "icon": "bell", "count": 2, "unread_count": 1},
            ],
        )
