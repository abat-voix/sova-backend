from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import SystemRole, UserRole
from sova.catalog.tests.factories import OrganizationContactFactory, OrganizationFactory
from sova.core.tests.factories import UserFactory
from sova.interactions.models import InteractionContact
from sova.interactions.tests.factories import InteractionFactory


class InteractionContactsApiTestCase(APITestCase):
    """Тесты GET/POST /api/interactions/{id}/contacts/: должность — у контрагента взаимодействия."""

    def setUp(self) -> None:
        self.user = UserFactory()
        UserRole.objects.create(user=self.user, role=SystemRole.PLATFORM_ADMIN)
        self.client.force_authenticate(user=self.user)
        self.interaction = InteractionFactory(organization=OrganizationFactory())
        self.url = reverse("interactions:interaction-contacts", args=[self.interaction.pk])

    def test_list_shows_position_at_interaction_counterparty_without_n_plus_one(self) -> None:
        """Каждый контакт — с должностью именно в вузе взаимодействия; число запросов не зависит от числа контактов."""
        for index in range(3):
            link = OrganizationContactFactory(organization=self.interaction.organization, position=f"Должность {index}")
            OrganizationContactFactory(contact=link.contact, position="В другом вузе")
            InteractionContact.objects.create(interaction=self.interaction, contact_person=link.contact)

        with self.assertNumQueries(self._list_queries()):
            response = self.client.get(self.url)

        # Проверяем должности у вуза взаимодействия
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [item["contact_person"]["position"] for item in response.data],
            ["Должность 0", "Должность 1", "Должность 2"],
        )

    def test_link_contact_of_other_organization_returns_409(self) -> None:
        """Человек без связи с вузом взаимодействия не привязывается."""
        link = OrganizationContactFactory()

        response = self.client.post(self.url, {"contact_person": str(link.contact_id)}, format="json")

        # Проверяем код ошибки
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_link_returns_position(self) -> None:
        """Ответ привязки содержит должность в вузе взаимодействия."""
        link = OrganizationContactFactory(organization=self.interaction.organization, position="Проректор")

        response = self.client.post(self.url, {"contact_person": str(link.contact_id)}, format="json")

        # Проверяем должность в ответе
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
        self.assertEqual(response.data["contact_person"]["position"], "Проректор")

    def _list_queries(self) -> int:
        """Число запросов списка с одним контактом — эталон для списка с несколькими."""
        link = OrganizationContactFactory(organization=self.interaction.organization)
        contact = InteractionContact.objects.create(interaction=self.interaction, contact_person=link.contact)
        with CaptureQueriesContext(connection) as context:
            self.client.get(self.url)
        contact.delete()
        link.delete()
        link.contact.delete()
        return len(context.captured_queries)
