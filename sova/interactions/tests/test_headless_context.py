from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from sova.catalog.tests.factories import DirectionFactory, ProductFactory, ProgramFactory, OrganizationFactory
from sova.interactions.models import Contract, InteractionDirection, InteractionProduct, InteractionProgram
from sova.interactions.tests.factories import ContractFactory, InteractionFactory


class HeadlessContextTestCase(TestCase):
    """Направление/программа/продукт взаимодействия могут временно висеть на договоре без Interaction."""

    def _headless_contract(self) -> Contract:
        return ContractFactory(interaction=None, organization=OrganizationFactory())

    def test_headless_interaction_product_requires_contract_or_interaction(self) -> None:
        with transaction.atomic(), self.assertRaises(IntegrityError):
            InteractionProduct.objects.create(product=ProductFactory())

    def test_headless_interaction_product_is_valid_with_contract_only(self) -> None:
        contract = self._headless_contract()
        item = InteractionProduct.objects.create(contract=contract, product=ProductFactory())
        item.full_clean()
        self.assertIsNone(item.interaction_id)

    def test_unique_product_per_contract_when_headless(self) -> None:
        contract = self._headless_contract()
        product = ProductFactory()
        InteractionProduct.objects.create(contract=contract, product=product)
        with transaction.atomic(), self.assertRaises(IntegrityError):
            InteractionProduct.objects.create(contract=contract, product=product)

    def test_headless_interaction_direction_and_program(self) -> None:
        contract = self._headless_contract()
        direction = InteractionDirection.objects.create(contract=contract, direction=DirectionFactory())
        program = InteractionProgram.objects.create(contract=contract, program=ProgramFactory())
        direction.full_clean()
        program.full_clean()

    def test_clean_rejects_program_from_another_contract(self) -> None:
        contract_a = self._headless_contract()
        contract_b = self._headless_contract()
        program = InteractionProgram.objects.create(contract=contract_a, program=ProgramFactory())
        product = InteractionProduct(contract=contract_b, interaction_program=program, product=ProductFactory())
        with self.assertRaises(ValidationError):
            product.full_clean()

    def test_attaching_interaction_still_enforces_unique_product_per_interaction(self) -> None:
        interaction = InteractionFactory()
        product = ProductFactory()
        InteractionProduct.objects.create(interaction=interaction, product=product)
        with transaction.atomic(), self.assertRaises(IntegrityError):
            InteractionProduct.objects.create(interaction=interaction, product=product)
