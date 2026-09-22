from django.core.exceptions import ValidationError
from django.test import TestCase

from sova.catalog.tests.factories import UniversityFactory
from sova.core.tests.factories import UserFactory
from sova.interactions.exceptions import AmbiguousManagerError, ManagerNotFoundError
from sova.interactions.models import InteractionProduct, Responsible
from sova.interactions.services.contract_attachment import contract_attachment_service
from sova.interactions.tests.factories import ContractFactory, InteractionFactory, InteractionProductFactory


class AttachToNewInteractionTestCase(TestCase):
    """Привязка headless-договора создаёт Interaction и перекладывает на него безголовые записи."""

    def setUp(self) -> None:
        self.university = UniversityFactory()
        self.manager = UserFactory(first_name="Иван", last_name="Иванов")
        self.contract = ContractFactory(
            interaction=None,
            university=self.university,
            draft_manager_full_name="Иванов Иван",
            draft_comment="Первичный контакт",
        )
        InteractionProductFactory(contract=self.contract, interaction=None)

    def test_creates_interaction_and_attaches_headless_records(self) -> None:
        interaction = contract_attachment_service.attach_to_new_interaction(
            contract=self.contract, assigned_by=self.manager
        )

        self.contract.refresh_from_db()
        self.assertEqual(self.contract.interaction_id, interaction.id)
        self.assertEqual(interaction.university_id, self.university.id)
        self.assertEqual(interaction.comment, "Первичный контакт")

        item = InteractionProduct.objects.get(contract=self.contract)
        self.assertEqual(item.interaction_id, interaction.id)

        responsible = Responsible.objects.get(interaction=interaction, unassigned_at__isnull=True)
        self.assertEqual(responsible.manager_id, self.manager.id)

    def test_manager_full_name_matches_regardless_of_word_order(self) -> None:
        """draft_manager_full_name хранится «Фамилия Имя», get_full_name() — «Имя Фамилия»."""
        self.contract.draft_manager_full_name = "  иван   ИВАНОВ "
        self.contract.save(update_fields=["draft_manager_full_name"])

        interaction = contract_attachment_service.attach_to_new_interaction(
            contract=self.contract, assigned_by=self.manager
        )

        self.assertTrue(Responsible.objects.filter(interaction=interaction, manager=self.manager).exists())

    def test_unknown_manager_raises(self) -> None:
        self.contract.draft_manager_full_name = "Несуществующий Менеджер"
        self.contract.save(update_fields=["draft_manager_full_name"])

        with self.assertRaises(ManagerNotFoundError):
            contract_attachment_service.attach_to_new_interaction(contract=self.contract, assigned_by=self.manager)

    def test_ambiguous_manager_raises(self) -> None:
        UserFactory(first_name="Иван", last_name="Иванов")  # тёзка self.manager

        with self.assertRaises(AmbiguousManagerError):
            contract_attachment_service.attach_to_new_interaction(contract=self.contract, assigned_by=self.manager)


class AttachToExistingInteractionTestCase(TestCase):
    """Привязка договора к уже существующему Interaction не трогает comment/Responsible."""

    def test_attaches_products_without_touching_comment_or_responsible(self) -> None:
        interaction = InteractionFactory(university=UniversityFactory(), comment="Исходный комментарий")
        contract = ContractFactory(
            interaction=None,
            university=interaction.university,
            draft_comment="Комментарий из второго договора",
        )
        InteractionProductFactory(contract=contract, interaction=None)

        contract_attachment_service.attach_to_existing_interaction(contract=contract, interaction=interaction)

        contract.refresh_from_db()
        interaction.refresh_from_db()
        self.assertEqual(contract.interaction_id, interaction.id)
        self.assertEqual(interaction.comment, "Исходный комментарий")
        self.assertFalse(Responsible.objects.filter(interaction=interaction).exists())
        self.assertTrue(InteractionProduct.objects.filter(contract=contract, interaction=interaction).exists())

    def test_rejects_interaction_with_another_counterparty(self) -> None:
        interaction = InteractionFactory(university=UniversityFactory())
        contract = ContractFactory(interaction=None, university=UniversityFactory())

        with self.assertRaises(ValidationError):
            contract_attachment_service.attach_to_existing_interaction(contract=contract, interaction=interaction)

        contract.refresh_from_db()
        self.assertIsNone(contract.interaction_id)
