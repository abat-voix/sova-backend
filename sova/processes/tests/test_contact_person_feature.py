from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import SystemRole, UserRole
from sova.catalog.models import ContactPerson, OrganizationContact
from sova.catalog.tests.factories import OrganizationContactFactory, OrganizationFactory
from sova.core.tests.factories import UserFactory
from sova.interactions.models import InteractionContact
from sova.interactions.tests.factories import InteractionFactory
from sova.processes.tests.factories import ActionInstanceFactory
from sova.workflows.tests.factories import ActionFeatureFactory


class ContactPersonFeatureApiTestCase(APITestCase):
    """Features `contact_person.create` / `contact_person.link`: связь с контрагентом взаимодействия."""

    def setUp(self) -> None:
        self.user = UserFactory()
        UserRole.objects.create(user=self.user, role=SystemRole.PLATFORM_ADMIN)
        self.client.force_authenticate(user=self.user)

        self.interaction = InteractionFactory(organization=OrganizationFactory())
        self.action_instance = ActionInstanceFactory(
            stage_instance__workflow_instance__interaction=self.interaction,
        )
        for code in (
            "contact_person.create",
            "contact_person.link",
            "contact_person.update",
            "contact_person.deactivate",
        ):
            ActionFeatureFactory(action=self.action_instance.action, code=code)

    def _execute(self, code: str, data: dict):
        return self.client.post(
            f"/api/processes/action-instances/{self.action_instance.pk}/features/{code}/execute/",
            data,
            format="json",
        )

    def test_create_makes_person_affiliation_and_link(self) -> None:
        """Человек создаётся со связью с вузом взаимодействия (должность — в связи) и сразу привязывается."""
        response = self._execute(
            "contact_person.create",
            {"full_name": "Иванов Иван", "position": "Проректор", "telegram": "@ivanov_ii"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
        link = OrganizationContact.objects.select_related("contact").get()
        self.assertEqual((link.organization_id, link.position), (self.interaction.organization_id, "Проректор"))
        self.assertEqual(link.contact.telegram, "ivanov_ii")
        self.assertTrue(InteractionContact.objects.filter(interaction=self.interaction, contact_person=link.contact).exists())
        self.assertEqual(response.data["target"]["data"]["position"], "Проректор")

    def test_create_invalid_data_saves_nothing(self) -> None:
        """Ошибка валидации не оставляет ни человека, ни связи."""
        response = self._execute("contact_person.create", {"full_name": "", "position": "Проректор"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(ContactPerson.objects.exists())

    def test_link_returns_position_of_interaction_counterparty(self) -> None:
        """При привязке должность — из связи с вузом взаимодействия, а не из другой связи человека."""
        link = OrganizationContactFactory(organization=self.interaction.organization, position="Проректор")
        OrganizationContactFactory(contact=link.contact, position="Доцент")

        response = self._execute("contact_person.link", {"contact_person": str(link.contact_id)})

        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
        self.assertEqual(response.data["target"]["data"]["position"], "Проректор")

    def test_link_contact_of_other_organization_returns_409(self) -> None:
        """Человек без связи с контрагентом взаимодействия не привязывается."""
        link = OrganizationContactFactory()

        response = self._execute("contact_person.link", {"contact_person": str(link.contact_id)})

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertFalse(InteractionContact.objects.exists())

    def test_link_inactive_contact_returns_400(self) -> None:
        """Выключенного человека нельзя привязать, даже если связь с контрагентом есть."""
        link = OrganizationContactFactory(organization=self.interaction.organization, contact__is_active=False)

        response = self._execute("contact_person.link", {"contact_person": str(link.contact_id)})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(InteractionContact.objects.exists())

    def test_update_changes_person_and_position_for_interaction_counterparty(self) -> None:
        """Общие данные меняются у человека, должность — только в связи с текущим вузом."""
        affiliation = OrganizationContactFactory(
            organization=self.interaction.organization,
            position="Менеджер",
            contact__telegram="old_name",
        )
        other_affiliation = OrganizationContactFactory(contact=affiliation.contact, position="Доцент")
        InteractionContact.objects.create(interaction=self.interaction, contact_person=affiliation.contact)

        response = self._execute(
            "contact_person.update",
            {
                "contact_person": str(affiliation.contact_id),
                "full_name": "Иванов Иван Иванович",
                "position": "Проректор",
                "telegram": "@new_name",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
        affiliation.refresh_from_db()
        other_affiliation.refresh_from_db()
        affiliation.contact.refresh_from_db()
        self.assertEqual(affiliation.position, "Проректор")
        self.assertEqual(other_affiliation.position, "Доцент")
        self.assertEqual(affiliation.contact.full_name, "Иванов Иван Иванович")
        self.assertEqual(affiliation.contact.telegram, "new_name")
        self.assertEqual(response.data["target"]["data"]["position"], "Проректор")

    def test_deactivate_unlinks_contact_and_deletes_all_affiliations(self) -> None:
        """Деактивация из feature означает уход человека из всех организаций."""
        affiliation = OrganizationContactFactory(organization=self.interaction.organization, position="Проректор")
        OrganizationContactFactory(contact=affiliation.contact)
        interaction_link = InteractionContact.objects.create(
            interaction=self.interaction,
            contact_person=affiliation.contact,
        )

        response = self._execute(
            "contact_person.deactivate",
            {"contact_person": str(affiliation.contact_id)},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
        affiliation.contact.refresh_from_db()
        interaction_link.refresh_from_db()
        self.assertFalse(affiliation.contact.is_active)
        self.assertIsNotNone(interaction_link.unlinked_at)
        self.assertFalse(OrganizationContact.objects.filter(contact=affiliation.contact).exists())
        self.assertEqual(response.data["target"]["data"]["position"], "Проректор")
