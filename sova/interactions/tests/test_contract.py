from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from sova.catalog.tests.factories import B2CClientFactory, OrganizationFactory
from sova.interactions.models import Contract
from sova.interactions.tests.factories import ContractFactory, InteractionFactory


class HeadlessContractTestCase(TestCase):
    """Договор может существовать без Interaction, но всегда с ровно одним контрагентом."""

    def test_headless_contract_without_interaction_is_valid(self) -> None:
        organization = OrganizationFactory()
        contract = Contract.objects.create(
            contract_number="Д-1",
            organization=organization,
            interaction=None,
        )
        contract.full_clean()
        self.assertIsNone(contract.interaction_id)

    def test_requires_exactly_one_counterparty_both_set(self) -> None:
        with transaction.atomic(), self.assertRaises(IntegrityError):
            Contract.objects.create(
                contract_number="Д-2",
                organization=OrganizationFactory(),
                b2c_client=B2CClientFactory(),
            )

    def test_requires_exactly_one_counterparty_none_set(self) -> None:
        with transaction.atomic(), self.assertRaises(IntegrityError):
            Contract.objects.create(contract_number="Д-3")

    def test_counterparty_copied_from_interaction_when_not_set(self) -> None:
        interaction = InteractionFactory(organization=OrganizationFactory())
        contract = Contract.objects.create(contract_number="Д-4", interaction=interaction)
        self.assertEqual(contract.organization_id, interaction.organization_id)
        self.assertIsNone(contract.b2c_client_id)

    def test_clean_rejects_mismatched_organization_when_interaction_set(self) -> None:
        interaction = InteractionFactory(organization=OrganizationFactory())
        contract = ContractFactory.build(
            interaction=interaction,
            organization=OrganizationFactory(),  # другой вуз, чем у interaction
            b2c_client=None,
        )
        with self.assertRaises(ValidationError):
            contract.full_clean()
