from uuid import uuid4

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import SystemRole, UserRole
from sova.catalog.tests.factories import DirectionFactory, UniversityFactory
from sova.core.tests.factories import UserFactory
from sova.interactions.models import Interaction, InteractionDirection
from sova.interactions.services import responsible_service
from sova.interactions.tests.factories import InteractionDirectionFactory, InteractionFactory


def create_user(role: str | None = None, **kwargs):
    """Создаёт пользователя и при необходимости назначает ему роль СОВА."""
    user = UserFactory(**kwargs)
    if role is not None:
        UserRole.objects.create(user=user, role=role)
    return user


class InteractionPermissionsTestCase(APITestCase):
    """
    Права на раздел взаимодействий по ролям (`accounts.policy`).

    Взаимодействие `self.foreign` принадлежит КАМу чужой команды — «чужое» для всех, кроме наблюдателя,
    администратора и superuser.
    """

    list_url = reverse("interactions:interaction-list")
    directions_url = reverse("interactions:interaction-direction-list")
    responsibles_url = reverse("interactions:responsible-list")

    def setUp(self) -> None:
        self.kam = create_user(SystemRole.KAM)
        self.foreign = InteractionFactory()
        responsible_service.assign(interaction=self.foreign, manager=self.kam, assigned_by=None)
        self.direction = InteractionDirectionFactory(interaction=self.foreign)

    def url(self, name: str, *args) -> str:
        """URL действия взаимодействия `self.foreign`."""
        return reverse(f"interactions:interaction-{name}", args=(self.foreign.pk, *args))

    def ids(self, response) -> set[str]:
        """Идентификаторы записей из ответа списка."""
        return {str(item["id"]) for item in response.data["results"]}

    def write_requests(self) -> dict[str, tuple[str, str, dict]]:
        """Все запросы, меняющие взаимодействие: имя -> (метод, URL, тело)."""
        return {
            "create": ("post", self.list_url, {"university": str(UniversityFactory().pk)}),
            "update": ("patch", self.url("detail"), {"comment": "изменено"}),
            "delete": ("delete", self.url("detail"), {}),
            "assignable_managers": ("get", self.url("assignable-managers"), {}),
            "assign": ("post", self.url("assign-responsible"), {"manager": self.kam.pk}),
            "unassign": ("post", self.url("unassign-responsible"), {"manager": self.kam.pk}),
            "link_contact": ("post", self.url("contacts"), {"contact_person": str(uuid4())}),
            "unlink_contact": ("delete", self.url("unlink-contact", uuid4()), {}),
            "chat_get": ("get", self.url("chat"), {}),
            "chat_create": ("post", self.url("chat"), {"participant_ids": []}),
            "chat_participants": ("post", self.url("chat-participants"), {"participant_ids": []}),
            "direction_create": (
                "post",
                self.directions_url,
                {"interaction": str(self.foreign.pk), "direction": str(DirectionFactory().pk)},
            ),
            "direction_update": (
                "patch",
                reverse("interactions:interaction-direction-detail", args=(self.direction.pk,)),
                {"is_active": False},
            ),
            "direction_delete": (
                "delete",
                reverse("interactions:interaction-direction-detail", args=(self.direction.pk,)),
                {},
            ),
        }

    def send(self, method: str, url: str, data: dict):
        """Отправляет запрос от имени аутентифицированного клиента."""
        return getattr(self.client, method)(path=url, data=data, format="json")

    def test_observer_reads_every_interaction_and_its_parts(self) -> None:
        """Наблюдатель видит все взаимодействия, их состав, ответственных и контакты."""
        unassigned = InteractionFactory()
        self.client.force_authenticate(user=create_user(SystemRole.OBSERVER))

        response = self.client.get(path=self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.ids(response), {str(self.foreign.pk), str(unassigned.pk)})

        for url in (self.url("detail"), self.url("contacts")):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(path=url).status_code, status.HTTP_200_OK)

        self.assertEqual(self.ids(self.client.get(path=self.directions_url)), {str(self.direction.pk)})
        self.assertEqual(len(self.ids(self.client.get(path=self.responsibles_url))), 1)

    def test_observer_cannot_change_anything(self) -> None:
        """Любой запрос наблюдателя на изменение — 403, данные не меняются."""
        self.client.force_authenticate(user=create_user(SystemRole.OBSERVER))

        for name, (method, url, data) in self.write_requests().items():
            with self.subTest(request=name):
                response = self.send(method, url, data)
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.assertEqual(Interaction.objects.count(), 1)
        self.assertTrue(InteractionDirection.objects.filter(pk=self.direction.pk, is_active=True).exists())
        self.assertTrue(self.foreign.responsibles.filter(unassigned_at__isnull=True).exists())

    def test_observer_reads_enabled_sections_but_not_personal_notifications(self) -> None:
        """Наблюдатель читает договоры и процессы, но не личные уведомления."""
        self.client.force_authenticate(user=create_user(SystemRole.OBSERVER))

        for url_name in ("interactions:contract-list", "processes:action-instance-list"):
            with self.subTest(url=url_name):
                response = self.client.get(path=reverse(url_name))
                self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(
            self.client.get(path=reverse("notifications:api-root")).status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_users_without_role_are_forbidden(self) -> None:
        """Без прикладной роли, в том числе staff и неактивному администратору, раздел закрыт."""
        users = (
            create_user(),
            create_user(is_staff=True),
            create_user(SystemRole.PLATFORM_ADMIN, is_active=False),
        )
        for user in users:
            self.client.force_authenticate(user=user)
            with self.subTest(user=user):
                self.assertEqual(self.client.get(path=self.list_url).status_code, status.HTTP_403_FORBIDDEN)
                self.assertEqual(
                    self.send(*self.write_requests()["create"]).status_code,
                    status.HTTP_403_FORBIDDEN,
                )

    def test_anonymous_is_unauthorized(self) -> None:
        """Анонимный запрос отклоняется до проверки роли."""
        response = self.client.get(path=self.list_url)

        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_superuser_without_role_manages_any_interaction(self) -> None:
        """Superuser без прикладной роли видит, меняет и назначает, как администратор."""
        superuser = create_user(is_superuser=True)
        other_kam = create_user(SystemRole.KAM)
        self.client.force_authenticate(user=superuser)

        self.assertEqual(self.ids(self.client.get(path=self.list_url)), {str(self.foreign.pk)})
        self.assertEqual(
            self.send("patch", self.url("detail"), {"comment": "от superuser"}).status_code,
            status.HTTP_200_OK,
        )
        candidates = self.client.get(path=self.url("assignable-managers")).data
        self.assertIn(other_kam.pk, {candidate["manager"]["id"] for candidate in candidates})
        self.assertEqual(
            self.send("post", self.url("assign-responsible"), {"manager": other_kam.pk}).status_code,
            status.HTTP_201_CREATED,
        )
        self.assertEqual(
            self.send("post", self.url("unassign-responsible"), {"manager": self.kam.pk}).status_code,
            status.HTTP_200_OK,
        )

    def test_kam_cannot_reach_foreign_interaction_parts(self) -> None:
        """КАМ не видит состав и историю чужого взаимодействия и не может их менять."""
        self.client.force_authenticate(user=create_user(SystemRole.KAM))

        self.assertEqual(self.ids(self.client.get(path=self.directions_url)), set())
        self.assertEqual(self.ids(self.client.get(path=self.responsibles_url)), set())

        requests = self.write_requests()
        # Чужое взаимодействие в теле запроса — как несуществующее
        self.assertEqual(self.send(*requests["direction_create"]).status_code, status.HTTP_400_BAD_REQUEST)
        # Чужая запись состава по ссылке — 404
        self.assertEqual(self.send(*requests["direction_update"]).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.send(*requests["direction_delete"]).status_code, status.HTTP_404_NOT_FOUND)

    def test_kam_changes_parts_of_own_interaction(self) -> None:
        """Состав своего взаимодействия КАМ меняет."""
        self.client.force_authenticate(user=self.kam)

        for name in ("direction_create", "direction_update"):
            with self.subTest(request=name):
                response = self.send(*self.write_requests()[name])
                self.assertIn(response.status_code, (status.HTTP_200_OK, status.HTTP_201_CREATED))

    def test_session_lists_allowed_actions(self) -> None:
        """`/api/auth/me/` отдаёт клиенту разрешённые операции роли."""
        self.client.force_login(create_user(SystemRole.OBSERVER))

        response = self.client.get(path=reverse("accounts:session"))

        self.assertEqual(
            response.json()["user"]["permissions"],
            sorted(
                {
                    "catalog.read",
                    "contracts.read",
                    "interactions.read",
                    "licenses.read",
                    "processes.read",
                    "reports.export",
                    "reports.read",
                    "training.read",
                }
            ),
        )
        self.assertFalse(response.json()["user"]["isSuperuser"])
