from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import SystemRole, UserRole
from sova.catalog.tests.factories import UniversityFactory
from sova.core.tests.factories import UserFactory
from sova.interactions.services import responsible_service
from sova.interactions.tests.factories import InteractionFactory


class InteractionVisibilityApiTestCase(APITestCase):
    """Тесты /api/interactions/interactions/ — состав выборки по роли запрашивающего."""

    list_url = reverse("interactions:interaction-list")

    @staticmethod
    def create_user(role: str | None = None, **kwargs):
        """Создаёт пользователя и при необходимости назначает ему роль СОВА."""
        user = UserFactory(**kwargs)
        if role is not None:
            UserRole.objects.create(user=user, role=role)
        return user

    @staticmethod
    def create_interaction(manager=None):
        """Создаёт взаимодействие, при указании менеджера — с действующим ответственным."""
        interaction = InteractionFactory()
        if manager is not None:
            responsible_service.assign(interaction=interaction, manager=manager, assigned_by=None)
        return interaction

    def response_ids(self, response) -> set[str]:
        """Идентификаторы взаимодействий из ответа списка."""
        return {item["id"] for item in response.data["results"]}

    def test_kam_sees_only_his_own_and_unassigned(self) -> None:
        """КАМ видит взаимодействия, где он ответственный, и ничьи."""
        kam = self.create_user(SystemRole.KAM)
        own = self.create_interaction(manager=kam)
        unassigned = self.create_interaction()
        another = self.create_interaction(manager=self.create_user(SystemRole.KAM))
        self.client.force_authenticate(user=kam)

        response = self.client.get(path=self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.response_ids(response), {str(own.pk), str(unassigned.pk)})
        self.assertNotIn(str(another.pk), self.response_ids(response))

    def test_head_sees_his_own_and_kams(self) -> None:
        """Руководитель видит свои взаимодействия и взаимодействия КАМов, но не чужих руководителей."""
        head = self.create_user(SystemRole.HEAD)
        own = self.create_interaction(manager=head)
        kam_interaction = self.create_interaction(manager=self.create_user(SystemRole.KAM))
        another_head = self.create_interaction(manager=self.create_user(SystemRole.HEAD))
        self.client.force_authenticate(user=head)

        response = self.client.get(path=self.list_url)

        self.assertEqual(self.response_ids(response), {str(own.pk), str(kam_interaction.pk)})
        self.assertNotIn(str(another_head.pk), self.response_ids(response))

    def test_platform_admin_sees_everything(self) -> None:
        """Администратор платформы видит все взаимодействия, включая чужие."""
        admin = self.create_user(SystemRole.PLATFORM_ADMIN)
        kam_interaction = self.create_interaction(manager=self.create_user(SystemRole.KAM))
        head_interaction = self.create_interaction(manager=self.create_user(SystemRole.HEAD))
        unassigned = self.create_interaction()
        self.client.force_authenticate(user=admin)

        response = self.client.get(path=self.list_url)

        self.assertEqual(
            self.response_ids(response),
            {str(kam_interaction.pk), str(head_interaction.pk), str(unassigned.pk)},
        )

    def test_user_without_role_sees_nothing(self) -> None:
        """Пользователю без прикладной роли список не даёт ничего."""
        self.create_interaction()
        self.client.force_authenticate(user=self.create_user())

        response = self.client.get(path=self.list_url)

        self.assertEqual(self.response_ids(response), set())

    def test_foreign_interaction_is_not_retrievable(self) -> None:
        """Чужое взаимодействие недоступно и по прямой ссылке, а не только скрыто из списка."""
        kam = self.create_user(SystemRole.KAM)
        another = self.create_interaction(manager=self.create_user(SystemRole.KAM))
        self.client.force_authenticate(user=kam)

        response = self.client.get(path=reverse("interactions:interaction-detail", args=(another.pk,)))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_unassigned_interaction_returns_to_the_kam_after_reassignment(self) -> None:
        """Снятый с ответственности КАМ видит взаимодействие как ничьё, а после передачи — нет."""
        kam = self.create_user(SystemRole.KAM)
        interaction = self.create_interaction(manager=kam)
        responsible_service.unassign(interaction=interaction, manager=kam)
        self.client.force_authenticate(user=kam)

        response = self.client.get(path=self.list_url)
        self.assertEqual(self.response_ids(response), {str(interaction.pk)})

        responsible_service.assign(
            interaction=interaction,
            manager=self.create_user(SystemRole.KAM),
            assigned_by=None,
        )

        response = self.client.get(path=self.list_url)
        self.assertEqual(self.response_ids(response), set())

    def test_each_of_several_kams_sees_the_interaction(self) -> None:
        """Каждый из действующих КАМов видит взаимодействие; снятый — перестаёт, пока остаётся второй."""
        first = self.create_user(SystemRole.KAM)
        second = self.create_user(SystemRole.KAM)
        interaction = self.create_interaction(manager=first)
        responsible_service.assign(interaction=interaction, manager=second, assigned_by=None)

        for kam in (first, second):
            self.client.force_authenticate(user=kam)
            response = self.client.get(path=self.list_url)
            self.assertEqual(self.response_ids(response), {str(interaction.pk)})

        responsible_service.unassign(interaction=interaction, manager=first)
        self.client.force_authenticate(user=first)

        response = self.client.get(path=self.list_url)
        self.assertEqual(self.response_ids(response), set())

    def test_created_interaction_is_returned_to_its_author(self) -> None:
        """Ответ на создание приходит автору, хотя ответственный ещё не назначен."""
        kam = self.create_user(SystemRole.KAM)
        university = UniversityFactory()
        self.client.force_authenticate(user=kam)

        response = self.client.post(
            path=self.list_url,
            data={"university": str(university.pk)},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("id", response.data)
