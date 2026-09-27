from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import SystemRole, UserRole

from sova.catalog.models import ContactPerson
from sova.catalog.tests.factories import ContactPersonFactory
from sova.core.tests.factories import UserFactory
from sova.interactions.models import InteractionContact
from sova.interactions.tests.factories import InteractionFactory
from sova.processes.models import ActionFeatureExecution
from sova.processes.tests.factories import ActionInstanceFactory
from sova.workflows.tests.factories import ActionFeatureFactory


class UpdateContactPersonFeatureApiTestCase(APITestCase):
    """Feature `contact_person.update` меняет только контакт текущего взаимодействия."""

    def setUp(self) -> None:
        self.user = UserFactory()
        UserRole.objects.create(user=self.user, role=SystemRole.PLATFORM_ADMIN)
        self.client.force_authenticate(user=self.user)
        self.interaction = InteractionFactory()
        self.action_instance = ActionInstanceFactory(
            stage_instance__workflow_instance__interaction=self.interaction,
        )
        ActionFeatureFactory(
            action=self.action_instance.action,
            code="contact_person.update",
        )
        self.url = (
            f"/api/processes/action-instances/{self.action_instance.pk}"
            "/features/contact_person.update/execute/"
        )

    def test_updates_a_linked_contact_and_records_the_execution(self) -> None:
        contact = ContactPersonFactory(
            university=self.interaction.university,
            full_name="Старое имя",
            position="Специалист",
            email="old@example.test",
            phone="+79990000000",
        )
        InteractionContact.objects.create(
            interaction=self.interaction,
            contact_person=contact,
        )

        response = self.client.post(
            self.url,
            {
                "contact_person": str(contact.pk),
                "full_name": "Новое имя",
                "position": "Руководитель",
                "email": "new@example.test",
                "phone": "+79991112233",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
        contact.refresh_from_db()
        self.assertEqual(contact.full_name, "Новое имя")
        self.assertEqual(contact.position, "Руководитель")
        self.assertEqual(response.data["target"]["data"]["email"], "new@example.test")
        execution = ActionFeatureExecution.objects.get()
        self.assertEqual(execution.feature_code_snapshot, "contact_person.update")
        self.assertEqual(execution.target_id, contact.pk)

    def test_rejects_a_contact_that_is_not_linked_to_the_interaction(self) -> None:
        contact = ContactPersonFactory(university=self.interaction.university)

        response = self.client.post(
            self.url,
            {"contact_person": str(contact.pk), "full_name": "Новое имя"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, msg=response.data)
        self.assertEqual(ContactPerson.objects.get(pk=contact.pk).full_name, contact.full_name)
        self.assertFalse(ActionFeatureExecution.objects.exists())

    def test_deactivates_a_linked_contact(self) -> None:
        contact = ContactPersonFactory(university=self.interaction.university)
        InteractionContact.objects.create(
            interaction=self.interaction,
            contact_person=contact,
        )
        ActionFeatureFactory(
            action=self.action_instance.action,
            code="contact_person.deactivate",
            sort_order=100,
        )
        url = (
            f"/api/processes/action-instances/{self.action_instance.pk}"
            "/features/contact_person.deactivate/execute/"
        )

        response = self.client.post(
            url,
            {"contact_person": str(contact.pk)},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
        contact.refresh_from_db()
        self.assertFalse(contact.is_active)
        self.assertEqual(
            ActionFeatureExecution.objects.get().feature_code_snapshot,
            "contact_person.deactivate",
        )
