from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import SystemRole, UserRole
from sova.catalog.models import ContactPerson, UniversityContact
from sova.catalog.tests.factories import UniversityContactFactory, UniversityFactory
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

        self.interaction = InteractionFactory(university=UniversityFactory())
        self.action_instance = ActionInstanceFactory(
            stage_instance__workflow_instance__interaction=self.interaction,
        )
        for code in ("contact_person.create", "contact_person.link"):
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
        link = UniversityContact.objects.select_related("contact").get()
        self.assertEqual((link.university_id, link.position), (self.interaction.university_id, "Проректор"))
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
        link = UniversityContactFactory(university=self.interaction.university, position="Проректор")
        UniversityContactFactory(contact=link.contact, position="Доцент")

        response = self._execute("contact_person.link", {"contact_person": str(link.contact_id)})

        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
        self.assertEqual(response.data["target"]["data"]["position"], "Проректор")

    def test_link_contact_of_other_organization_returns_409(self) -> None:
        """Человек без связи с контрагентом взаимодействия не привязывается."""
        link = UniversityContactFactory()

        response = self._execute("contact_person.link", {"contact_person": str(link.contact_id)})

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertFalse(InteractionContact.objects.exists())

    def test_link_inactive_contact_returns_400(self) -> None:
        """Выключенного человека нельзя привязать, даже если связь с контрагентом есть."""
        link = UniversityContactFactory(university=self.interaction.university, contact__is_active=False)

        response = self._execute("contact_person.link", {"contact_person": str(link.contact_id)})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(InteractionContact.objects.exists())
