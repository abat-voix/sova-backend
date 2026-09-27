from unittest.mock import patch

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.exceptions import KamHasHeadError
from accounts.models import Supervision, SystemRole, UserRole
from accounts.services import get_system_role
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
        """Руководитель видит только КАМов и никого больше."""
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

    def test_head_sees_team_and_free_kams(self) -> None:
        """Руководитель видит свою команду и свободных КАМов, но не КАМов чужой команды."""
        head = self.create_user(SystemRole.HEAD)
        other_head = self.create_user(SystemRole.HEAD)
        mine = self.create_user(SystemRole.KAM)
        free = self.create_user(SystemRole.KAM)
        foreign = self.create_user(SystemRole.KAM)
        Supervision.objects.create(kam=mine, head=head)
        Supervision.objects.create(kam=foreign, head=other_head)
        self.client.force_authenticate(user=head)

        response = self.client.get(path=self.list_url)

        # Проверяем состав: своя команда и свободные
        self.assertEqual(self.response_ids(response), {mine.pk, free.pk})

    def test_team_filter(self) -> None:
        """`team=mine` — только своя команда, `team=free` — только свободные."""
        head = self.create_user(SystemRole.HEAD)
        mine = self.create_user(SystemRole.KAM)
        free = self.create_user(SystemRole.KAM)
        Supervision.objects.create(kam=mine, head=head)
        self.client.force_authenticate(user=head)

        # Проверяем оба значения фильтра
        self.assertEqual(self.response_ids(self.client.get(self.list_url, {"team": "mine"})), {mine.pk})
        self.assertEqual(self.response_ids(self.client.get(self.list_url, {"team": "free"})), {free.pk})

    def test_role_filter_accepts_several_roles(self) -> None:
        """`role` фильтрует по нескольким ролям сразу."""
        admin = self.create_user(SystemRole.PLATFORM_ADMIN)
        kam = self.create_user(SystemRole.KAM)
        head = self.create_user(SystemRole.HEAD)
        self.create_user()
        self.client.force_authenticate(user=admin)

        response = self.client.get(self.list_url, {"role": [SystemRole.KAM, SystemRole.HEAD]})

        # Проверяем, что админ и пользователь без роли отфильтрованы
        self.assertEqual(self.response_ids(response), {kam.pk, head.pk})

    def test_head_filter(self) -> None:
        """`head=<id>` — команда конкретного руководителя."""
        admin = self.create_user(SystemRole.PLATFORM_ADMIN)
        head = self.create_user(SystemRole.HEAD)
        kam = self.create_user(SystemRole.KAM)
        self.create_user(SystemRole.KAM)
        Supervision.objects.create(kam=kam, head=head)
        self.client.force_authenticate(user=admin)

        response = self.client.get(self.list_url, {"head": head.pk})

        # Проверяем, что в ответе только КАМ этого руководителя
        self.assertEqual(self.response_ids(response), {kam.pk})

    def test_platform_admin_sees_everyone(self) -> None:
        """Администратор платформы видит всех активных пользователей, включая администраторов."""
        admin = self.create_user(SystemRole.PLATFORM_ADMIN)
        another_admin = self.create_user(SystemRole.PLATFORM_ADMIN)
        kam = self.create_user(SystemRole.KAM)
        head = self.create_user(SystemRole.HEAD)
        roleless = self.create_user()
        self.client.force_authenticate(user=admin)

        response = self.client.get(path=self.list_url)

        # Проверяем успешный ответ
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Проверяем, что видны все, включая администраторов: ими тоже нужно управлять
        self.assertEqual(self.response_ids(response), {admin.pk, another_admin.pk, kam.pk, head.pk, roleless.pk})

    def test_platform_admin_can_list_inactive_users(self) -> None:
        """Неактивных администратор получает явным фильтром `is_active=false`."""
        admin = self.create_user(SystemRole.PLATFORM_ADMIN)
        inactive = self.create_user(SystemRole.KAM, is_active=False)
        self.client.force_authenticate(user=admin)

        response = self.client.get(path=self.list_url, data={"is_active": "false"})

        # Проверяем, что в списке только неактивный
        self.assertEqual(self.response_ids(response), {inactive.pk})

    def test_head_cannot_list_inactive_users(self) -> None:
        """Руководителю фильтр `is_active=false` неактивных не открывает."""
        head = self.create_user(SystemRole.HEAD)
        self.create_user(SystemRole.KAM, is_active=False)
        self.client.force_authenticate(user=head)

        response = self.client.get(path=self.list_url, data={"is_active": "false"})

        # Проверяем, что список пуст
        self.assertEqual(response.data["count"], 0)

    def test_inactive_users_are_hidden(self) -> None:
        """Отключённые учётные записи в списке не показываются."""
        head = self.create_user(SystemRole.HEAD)
        self.create_user(SystemRole.KAM, is_active=False)
        self.client.force_authenticate(user=head)

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
        head = self.create_user(SystemRole.HEAD, first_name="Филин", last_name="Филинов")
        kam = self.create_user(SystemRole.KAM, first_name="Сова", last_name="Совова")
        Supervision.objects.create(kam=kam, head=head)
        self.client.force_authenticate(user=admin)

        response = self.client.get(path=self.list_url, data={"search": "Совова"})

        # Проверяем состав полей элемента списка
        self.assertEqual(
            response.data["results"][0],
            {
                "id": kam.pk,
                "email": kam.email,
                "first_name": "Сова",
                "last_name": "Совова",
                "full_name": "Сова Совова",
                "is_active": True,
                "role": SystemRole.KAM.value,
                "role_display": "КАМ",
                "head": {"id": head.pk, "email": head.email, "full_name": "Филин Филинов"},
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

    def test_roles_dictionary(self) -> None:
        """Справочник ролей доступен руководителю и администратору платформы."""
        expected = [
            {"value": "observer", "label": "Наблюдатель"},
            {"value": "kam", "label": "КАМ"},
            {"value": "head", "label": "Руководитель"},
            {"value": "platform_admin", "label": "Администратор платформы"},
        ]
        for role in (SystemRole.HEAD, SystemRole.PLATFORM_ADMIN):
            self.client.force_authenticate(user=self.create_user(role))
            with self.subTest(role=role):
                response = self.client.get(path=reverse("users:user-roles"))

                # Проверяем состав справочника
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual(response.data, expected)

    def test_roles_dictionary_is_forbidden_to_kam(self) -> None:
        """КАМу справочник ролей недоступен, как и список пользователей."""
        self.client.force_authenticate(user=self.create_user(SystemRole.KAM))

        response = self.client.get(path=reverse("users:user-roles"))

        # Проверяем, что доступ запрещён
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


@patch("sova.notifications.services.event_notification.send_event_notification")
class UserManagementApiTestCase(APITestCase):
    """Тесты экшенов администратора платформы: роль, руководитель, активность."""

    def setUp(self) -> None:
        """Администратор, руководитель с КАМом и свободный руководитель."""
        self.admin = UserListApiTestCase.create_user(SystemRole.PLATFORM_ADMIN)
        self.head = UserListApiTestCase.create_user(SystemRole.HEAD, first_name="Анна", last_name="Смирнова")
        self.other_head = UserListApiTestCase.create_user(SystemRole.HEAD)
        self.kam = UserListApiTestCase.create_user(SystemRole.KAM, first_name="Иван", last_name="Иванов")
        Supervision.objects.create(kam=self.kam, head=self.head)
        self.client.force_authenticate(user=self.admin)

    @staticmethod
    def url(action: str, user) -> str:
        """Адрес экшена над пользователем."""
        return reverse(f"users:user-{action}", args=[user.pk])

    def test_change_role_returns_orphaned_kams(self, task) -> None:
        """Смена роли руководителя возвращает его бывшую команду."""
        response = self.client.put(self.url("role", self.head), {"role": SystemRole.KAM}, format="json")

        # Проверяем ответ: пользователь с новой ролью и осиротевшие КАМы
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["user"]["role"], SystemRole.KAM)
        self.assertEqual([kam["id"] for kam in response.data["orphaned_kams"]], [self.kam.pk])
        self.assertFalse(Supervision.objects.exists())

    def test_remove_role(self, task) -> None:
        """`role: null` снимает роль."""
        response = self.client.put(self.url("role", self.kam), {"role": None}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["user"]["role"])
        self.assertFalse(UserRole.objects.filter(user=self.kam).exists())

    def test_assign_role_to_user_without_role(self, task) -> None:
        """Пользователю без роли назначается роль."""
        roleless = UserListApiTestCase.create_user()

        response = self.client.put(self.url("role", roleless), {"role": SystemRole.HEAD}, format="json")

        # Проверяем ответ и назначенную роль
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["user"]["role"], SystemRole.HEAD)
        self.assertEqual(response.data["orphaned_kams"], [])
        self.assertEqual(UserRole.objects.get(user=roleless).role, SystemRole.HEAD)

    def test_invalid_role(self, task) -> None:
        """Неизвестная роль — 400."""
        response = self.client.put(self.url("role", self.kam), {"role": "owner"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_role_is_required(self, task) -> None:
        """Без поля `role` роль не меняется — 400."""
        response = self.client.put(self.url("role", self.kam), {}, format="json")

        # Проверяем ошибку и неизменную роль
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(UserRole.objects.get(user=self.kam).role, SystemRole.KAM)

    def test_unknown_user_returns_404(self, task) -> None:
        """Несуществующий пользователь — 404."""
        response = self.client.put(reverse("users:user-role", args=[999999]), {"role": SystemRole.HEAD}, format="json")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_admin_cannot_drop_own_admin_role(self, task) -> None:
        """Администратор не может снять с себя роль администратора."""
        response = self.client.put(self.url("role", self.admin), {"role": SystemRole.HEAD}, format="json")

        # Проверяем код ошибки и неизменную роль
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "self_lockout")
        self.assertEqual(UserRole.objects.get(user=self.admin).role, SystemRole.PLATFORM_ADMIN)

    def test_set_head(self, task) -> None:
        """Назначение руководителя КАМу."""
        response = self.client.put(self.url("head", self.kam), {"head": self.other_head.pk}, format="json")

        # Проверяем ответ и связь
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["user"]["head"]["id"], self.other_head.pk)
        self.assertEqual(response.data["orphaned_kams"], [])
        self.assertEqual(Supervision.objects.get(kam=self.kam).head, self.other_head)

    def test_remove_head(self, task) -> None:
        """`head: null` снимает руководителя."""
        response = self.client.put(self.url("head", self.kam), {"head": None}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["user"]["head"])
        self.assertFalse(Supervision.objects.exists())

    def test_head_must_be_head(self, task) -> None:
        """Руководителем нельзя назначить не-руководителя."""
        response = self.client.put(self.url("head", self.kam), {"head": self.admin.pk}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("head", response.data)

    def test_head_only_for_kam(self, task) -> None:
        """Руководителя назначают только КАМу."""
        response = self.client.put(self.url("head", self.other_head), {"head": self.head.pk}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "invalid_supervision")

    def test_deactivate(self, task) -> None:
        """Деактивация руководителя возвращает его команду."""
        response = self.client.post(self.url("deactivate", self.head))

        self.head.refresh_from_db()
        # Проверяем ответ и состояние
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["user"]["is_active"])
        self.assertEqual([kam["id"] for kam in response.data["orphaned_kams"]], [self.kam.pk])
        self.assertFalse(self.head.is_active)

    def test_admin_cannot_deactivate_self(self, task) -> None:
        """Администратор не может деактивировать себя."""
        response = self.client.post(self.url("deactivate", self.admin))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "self_lockout")

    def test_activate_inactive_user(self, task) -> None:
        """Администратор активирует неактивного пользователя — он доступен экшену."""
        self.kam.is_active = False
        self.kam.save()

        response = self.client.post(self.url("activate", self.kam))

        self.kam.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(self.kam.is_active)

    def test_only_platform_admin(self, task) -> None:
        """Руководителю, КАМу и пользователю без роли экшены недоступны."""
        for user in (self.head, self.kam, UserListApiTestCase.create_user()):
            self.client.force_authenticate(user=user)
            with self.subTest(role=get_system_role(user)):
                # Проверяем каждый экшен
                self.assertEqual(
                    self.client.put(self.url("role", self.kam), {"role": SystemRole.HEAD}, format="json").status_code,
                    status.HTTP_403_FORBIDDEN,
                )
                self.assertEqual(
                    self.client.put(self.url("head", self.kam), {"head": None}, format="json").status_code,
                    status.HTTP_403_FORBIDDEN,
                )
                self.assertEqual(self.client.post(self.url("deactivate", self.kam)).status_code, 403)
                self.assertEqual(self.client.post(self.url("activate", self.kam)).status_code, 403)
        # Проверяем, что ничего не изменилось
        self.assertEqual(UserRole.objects.get(user=self.kam).role, SystemRole.KAM)
        self.assertTrue(Supervision.objects.exists())


@patch("sova.notifications.services.event_notification.send_event_notification")
class TeamApiTestCase(APITestCase):
    """Руководитель ведёт свою команду: claim / release."""

    def setUp(self) -> None:
        """Руководитель, чужой руководитель, свободный и чужой КАМы."""
        self.head = UserListApiTestCase.create_user(SystemRole.HEAD)
        self.other_head = UserListApiTestCase.create_user(SystemRole.HEAD)
        self.free = UserListApiTestCase.create_user(SystemRole.KAM)
        self.foreign = UserListApiTestCase.create_user(SystemRole.KAM)
        Supervision.objects.create(kam=self.foreign, head=self.other_head)
        self.client.force_authenticate(user=self.head)

    @staticmethod
    def url(action: str, user) -> str:
        """Адрес экшена над пользователем."""
        return reverse(f"users:user-{action}", args=[user.pk])

    def test_claim_free_kam(self, task) -> None:
        """Свободный КАМ попадает в команду; в ответе — руководитель."""
        response = self.client.post(self.url("claim", self.free))

        # Проверяем ответ и связь
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
        self.assertEqual(response.data["head"]["id"], self.head.pk)
        self.assertEqual(Supervision.objects.get(kam=self.free).head, self.head)

    def test_claim_foreign_kam_is_404(self, task) -> None:
        """Чужой КАМ руководителю не виден."""
        response = self.client.post(self.url("claim", self.foreign))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_claim_race_returns_409(self, task) -> None:
        """КАМа забрали между списком и запросом — 409 `kam_has_head`."""
        with patch("accounts.api.views.account_service.claim", side_effect=KamHasHeadError):
            response = self.client.post(self.url("claim", self.free))

        # Проверяем код ошибки
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "kam_has_head")

    def test_release_own_kam(self, task) -> None:
        """Свой КАМ становится свободным."""
        Supervision.objects.create(kam=self.free, head=self.head)

        response = self.client.post(self.url("release", self.free))

        # Проверяем ответ и отсутствие связи
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
        self.assertIsNone(response.data["head"])
        self.assertFalse(Supervision.objects.filter(kam=self.free).exists())

    def test_release_free_kam_returns_409(self, task) -> None:
        """Свободного КАМа отпустить нельзя — 409 `not_in_team`."""
        response = self.client.post(self.url("release", self.free))

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "not_in_team")

    def test_only_head_can_claim(self, task) -> None:
        """Администратору и КАМу claim недоступен."""
        for role in (SystemRole.PLATFORM_ADMIN, SystemRole.KAM):
            self.client.force_authenticate(user=UserListApiTestCase.create_user(role))

            response = self.client.post(self.url("claim", self.free))

            # Проверяем запрет для роли
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, msg=role)
