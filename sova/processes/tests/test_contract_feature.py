from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import SystemRole, UserRole

from sova.catalog.tests.factories import ContactPersonFactory, UniversityFactory
from sova.core.tests.factories import UserFactory
from sova.interactions.enum import DocumentTemplateKind
from sova.interactions.models import Contract, DocumentTemplate, InteractionContact
from sova.interactions.tests.factories import InteractionFactory, InteractionProductFactory
from sova.processes.models import ActionFeatureExecution
from sova.processes.tests.factories import ActionInstanceFactory
from sova.workflows.tests.factories import ActionFeatureFactory


class CreateContractFeatureApiTestCase(APITestCase):
    """Feature `contract.create`: начальные данные формы и приём JSON договора (без файла)."""

    def setUp(self) -> None:
        self.user = UserFactory()
        UserRole.objects.create(user=self.user, role=SystemRole.PLATFORM_ADMIN)
        self.client.force_authenticate(user=self.user)

        university = UniversityFactory(short_name="ВУЗ", inn="7700000000", city="Москва")
        self.interaction = InteractionFactory(university=university)
        self.action_instance = ActionInstanceFactory(
            stage_instance__workflow_instance__interaction=self.interaction,
        )
        ActionFeatureFactory(action=self.action_instance.action, code="contract.create")
        self.template = DocumentTemplate.objects.get(kind=DocumentTemplateKind.CONTRACT)
        self.base_url = f"/api/processes/action-instances/{self.action_instance.pk}/features/contract.create"

    def payload(self, **document) -> dict:
        return {
            "template": str(self.template.pk),
            "document": {
                "contract_number": "Д-1",
                "contract_date": "2026-09-26",
                "counterparty": {"name": "Вуз", "inn": "7700000000"},
                "signatory": {"full_name": "Иванов И. И.", "position": "Ректор"},
                "products": ["Продукт"],
                "amount": "1000.50",
                **document,
            },
        }

    def test_initial_prefills_counterparty_contacts_and_products(self) -> None:
        contact = ContactPersonFactory(university=self.interaction.university, position="Ректор")
        InteractionContact.objects.create(interaction=self.interaction, contact_person=contact)
        product = InteractionProductFactory(interaction=self.interaction)

        response = self.client.get(f"{self.base_url}/initial/")

        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
        self.assertEqual(response.data["templates"], [{"id": self.template.pk, "name": "Договор"}])
        self.assertEqual(response.data["contacts"][0]["full_name"], contact.full_name)
        document = response.data["document"]
        self.assertEqual(document["counterparty"]["name"], self.interaction.university.name)
        self.assertEqual(document["counterparty"]["short_name"], "ВУЗ")
        self.assertEqual(document["counterparty"]["inn"], "7700000000")
        self.assertEqual(document["city"], "Москва")
        self.assertEqual(document["products"], [product.product.name])

    def test_execute_accepts_json_and_creates_contract_without_file(self) -> None:
        response = self.client.post(f"{self.base_url}/execute/", self.payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
        contract = Contract.objects.get(pk=response.data["target"]["id"])
        self.assertEqual(contract.interaction, self.interaction)
        self.assertEqual(contract.contract_number, "Д-1")
        self.assertFalse(contract.file)
        data = response.data["target"]["data"]
        self.assertFalse(data["file_generated"])
        self.assertEqual(data["document"]["contract_date"], "2026-09-26")
        self.assertEqual(data["document"]["amount"], "1000.50")
        self.assertEqual(data["document"]["signatory"]["full_name"], "Иванов И. И.")
        execution = ActionFeatureExecution.objects.get(pk=response.data["execution"]["id"])
        self.assertEqual(execution.result["document"]["counterparty"]["name"], "Вуз")

    def test_execute_requires_counterparty_name(self) -> None:
        response = self.client.post(
            f"{self.base_url}/execute/", self.payload(counterparty={"name": ""}), format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Contract.objects.exists())

    def test_execute_rejects_inactive_template(self) -> None:
        self.template.is_active = False
        self.template.save()

        response = self.client.post(f"{self.base_url}/execute/", self.payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Contract.objects.exists())

    def test_available_features_include_contract_create(self) -> None:
        response = self.client.get(f"/api/processes/action-instances/{self.action_instance.pk}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
        self.assertEqual([item["code"] for item in response.data["available_features"]], ["contract.create"])
