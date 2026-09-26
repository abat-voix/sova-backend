from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import SystemRole, UserRole
from sova.core.tests.factories import UserFactory


class UserListApiTestCase(APITestCase):
    """Тесты /api/users/ — список пользователей по роли запрашивающего."""

    list_url = reverse("users:user-list")

    @staticmethod
    def create_user(role: str | None = None, **kwargs):
        """Создаёт пользователя и при необходимости назначает ему роль СОВА."""
        user = UserFactory(**kwargs)
        if role is not None:
            UserRole.objects.create(user=user, role=role)
        return user

    def response_ids(self, response) -> set[int]:
        """Идентификаторы пользователей из ответа списка."""
        return {item["id"] for item in response.data["results"]}

    def test_head_sees_only_kams(self) -> None:
        """Руководитель видит всех КАМов и никого больше."""
        head = self.create_user(SystemRole.HEAD)
        kam = self.create_user(SystemRole.KAM)
        another_head = self.create_user(SystemRole.HEAD)
        admin = self.create_user(SystemRole.PLATFORM_ADMIN)
        roleless = self.create_user()
        self.client.force_authenticate(user=head)

        response = self.client.get(path=self.list_url)

        # Проверяем успешный ответ
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Проверяем, что в списке только КАМы
        self.assertEqual(self.response_ids(response), {kam.pk})
        self.assertNotIn(another_head.pk, self.response_ids(response))
        self.assertNotIn(admin.pk, self.response_ids(response))
        self.assertNotIn(roleless.pk, self.response_ids(response))

    def test_platform_admin_sees_everyone_except_platform_admins(self) -> None:
        """Администратор платформы видит всех активных пользователей, кроме себя."""
        admin = self.create_user(SystemRole.PLATFORM_ADMIN)
        another_admin = self.create_user(SystemRole.PLATFORM_ADMIN)
        kam = self.create_user(SystemRole.KAM)
        head = self.create_user(SystemRole.HEAD)
        roleless = self.create_user()
        self.client.force_authenticate(user=admin)

        response = self.client.get(path=self.list_url)

        # Проверяем успешный ответ
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Проверяем, что видны все, кроме самого администратора
        self.assertEqual(
            self.response_ids(response), {another_admin.pk, kam.pk, head.pk, roleless.pk}
        )
        self.assertNotIn(admin.pk, self.response_ids(response))

    def test_roles_dictionary_is_available_to_platform_admin(self) -> None:
        admin = self.create_user(SystemRole.PLATFORM_ADMIN)
        self.client.force_authenticate(user=admin)

        response = self.client.get(f"{self.list_url}roles/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data,
            [
                {"value": "kam", "label": "КАМ"},
                {"value": "head", "label": "Руководитель"},
                {"value": "platform_admin", "label": "Администратор платформы"},
            ],
        )

    def test_platform_admin_can_assign_update_and_remove_role(self) -> None:
        admin = self.create_user(SystemRole.PLATFORM_ADMIN)
        target = self.create_user()
        self.client.force_authenticate(user=admin)
        url = reverse("users:user-role", args=[target.pk])

        response = self.client.patch(url, {"role": SystemRole.HEAD}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["role"], SystemRole.HEAD)
        self.assertEqual(UserRole.objects.get(user=target).role, SystemRole.HEAD)

        response = self.client.patch(url, {"role": SystemRole.KAM}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(UserRole.objects.get(user=target).role, SystemRole.KAM)

        response = self.client.patch(url, {"role": None}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["role"])
        self.assertFalse(UserRole.objects.filter(user=target).exists())

    def test_role_command_rejects_self_inactive_and_unknown_users(self) -> None:
        admin = self.create_user(SystemRole.PLATFORM_ADMIN)
        inactive = self.create_user(is_active=False)
        self.client.force_authenticate(user=admin)

        self.assertEqual(
            self.client.patch(
                reverse("users:user-role", args=[admin.pk]),
                {"role": SystemRole.HEAD},
                format="json",
            ).status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            self.client.patch(
                reverse("users:user-role", args=[inactive.pk]),
                {"role": SystemRole.HEAD},
                format="json",
            ).status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            self.client.patch(
                reverse("users:user-role", args=[999999]),
                {"role": SystemRole.HEAD},
                format="json",
            ).status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_only_platform_admin_can_change_roles(self) -> None:
        head = self.create_user(SystemRole.HEAD)
        target = self.create_user()
        self.client.force_authenticate(user=head)

        response = self.client.patch(
            reverse("users:user-role", args=[target.pk]),
            {"role": SystemRole.KAM},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(UserRole.objects.filter(user=target).exists())

    def test_invalid_role_is_rejected(self) -> None:
        admin = self.create_user(SystemRole.PLATFORM_ADMIN)
        target = self.create_user()
        self.client.force_authenticate(user=admin)

        response = self.client.patch(
            reverse("users:user-role", args=[target.pk]),
            {"role": "unknown"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(UserRole.objects.filter(user=target).exists())

    def test_inactive_users_are_hidden(self) -> None:
        """Отключённые учётные записи в списке не показываются."""
        admin = self.create_user(SystemRole.PLATFORM_ADMIN)
        self.create_user(SystemRole.KAM, is_active=False)
        self.client.force_authenticate(user=admin)

        response = self.client.get(path=self.list_url)

        # Проверяем, что список пуст
        self.assertEqual(response.data["count"], 0)

    def test_kam_cannot_list_users(self) -> None:
        """КАМу список пользователей недоступен."""
        self.client.force_authenticate(user=self.create_user(SystemRole.KAM))

        response = self.client.get(path=self.list_url)

        # Проверяем, что доступ запрещён
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_user_without_role_cannot_list_users(self) -> None:
        """Пользователю без роли СОВА список пользователей недоступен."""
        self.client.force_authenticate(user=self.create_user())

        response = self.client.get(path=self.list_url)

        # Проверяем, что доступ запрещён
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_request_is_rejected(self) -> None:
        """Анонимный запрос списка отклоняется."""
        response = self.client.get(path=self.list_url)

        # Проверяем, что доступ запрещён
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

    def test_list_item_contains_role_and_name(self) -> None:
        """Элемент списка содержит ФИО, почту и роль пользователя."""
        admin = self.create_user(SystemRole.PLATFORM_ADMIN)
        kam = self.create_user(SystemRole.KAM, first_name="Сова", last_name="Совова")
        self.client.force_authenticate(user=admin)

        response = self.client.get(path=self.list_url)

        # Проверяем состав полей элемента списка
        self.assertEqual(
            response.data["results"][0],
            {
                "id": kam.pk,
                "email": kam.email,
                "first_name": "Сова",
                "last_name": "Совова",
                "full_name": "Сова Совова",
                "role": SystemRole.KAM.value,
                "role_display": "КАМ",
            },
        )

    def test_search_finds_user_by_last_name(self) -> None:
        """Поиск отбирает пользователей по фамилии."""
        admin = self.create_user(SystemRole.PLATFORM_ADMIN)
        kam = self.create_user(SystemRole.KAM, last_name="Филинов")
        self.create_user(SystemRole.KAM, last_name="Сычёв")
        self.client.force_authenticate(user=admin)

        response = self.client.get(path=self.list_url, data={"search": "Филин"})

        # Проверяем, что найден только искомый пользователь
        self.assertEqual(self.response_ids(response), {kam.pk})

    def test_detail_of_hidden_user_returns_404(self) -> None:
        """Пользователь вне видимости роли недоступен и поштучно."""
        head = self.create_user(SystemRole.HEAD)
        hidden = self.create_user(SystemRole.PLATFORM_ADMIN)
        self.client.force_authenticate(user=head)

        response = self.client.get(
            path=reverse("users:user-detail", args=[hidden.pk])
        )

        # Проверяем, что объект не найден
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
