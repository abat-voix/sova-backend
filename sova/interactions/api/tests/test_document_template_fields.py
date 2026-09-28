from types import SimpleNamespace

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import SystemRole, UserRole
from sova.core.tests.factories import UserFactory
from sova.interactions.tests.factories import (
    ContractFactory,
    InteractionDirectionFactory,
    InteractionFactory,
    InteractionProductFactory,
    InteractionProgramFactory,
    LicenseFactory,
)
from sova.processes.action_features.handlers.contract import (
    ContractDocumentSerializer,
    CreateContractHandler,
)


def _paths(value: dict, prefix: str = "") -> set[str]:
    paths = set()
    for name, item in value.items():
        path = f"{prefix}.{name}" if prefix else name
        paths.add(path)
        if isinstance(item, dict):
            paths.update(_paths(item, path))
        elif isinstance(item, list) and item:
            paths.update(_paths(item[0], f"{path}[]"))
    return paths


class DocumentTemplateFieldsApiTestCase(APITestCase):
    def setUp(self) -> None:
        self.url = reverse("interactions:document-template-fields")
        self.user = UserFactory()
        UserRole.objects.create(user=self.user, role=SystemRole.PLATFORM_ADMIN)
        self.client.force_authenticate(user=self.user)

    def test_catalog_matches_contract_document_context(self) -> None:
        interaction = InteractionFactory()
        InteractionDirectionFactory(interaction=interaction)
        program = InteractionProgramFactory(interaction=interaction)
        product = InteractionProductFactory(interaction=interaction, interaction_program=program)
        LicenseFactory(
            contract=ContractFactory(interaction=interaction),
            interaction_product=product,
        )
        context = SimpleNamespace(
            interaction=interaction,
            organization=interaction.organization,
            b2c_client=interaction.b2c_client,
        )
        document = CreateContractHandler().initial(context=context, settings={})["document"]

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["kind"], "contract")
        fields = response.data["fields"]
        self.assertEqual({field["path"] for field in fields}, _paths(document))
        self.assertEqual(
            {field["path"] for field in fields if "." not in field["path"] and "[]" not in field["path"]},
            set(ContractDocumentSerializer().fields),
        )
        self.assertEqual(len(fields), len({field["path"] for field in fields}))
        snippets = {field["path"]: field["snippet"] for field in fields}
        self.assertEqual(snippets["counterparty.name"], "{{ counterparty.name }}")
        self.assertEqual(
            snippets["products[].name"],
            "{% for product in products %}\n{{ product.name }}\n{% endfor %}",
        )
        self.assertIn("{% for product in products %}", snippets["products"])

    def test_only_contract_kind_is_supported(self) -> None:
        response = self.client.get(self.url, {"kind": "other"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("kind", response.data)

    def test_requires_authentication(self) -> None:
        self.client.force_authenticate(user=None)
        response = self.client.get(self.url)
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))
