from django.core.exceptions import ValidationError
from django.test import TestCase

from sova.catalog.tests.factories import UniversityFactory
from sova.core.tests.factories import UserFactory
from sova.interactions.exceptions import AmbiguousManagerError, ManagerNotFoundError
from sova.interactions.models import InteractionProduct, Responsible
from sova.interactions.services import responsible_service
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
            contract=self.contract, assigned_by=self.manager, manager=self.manager
        )

        self.contract.refresh_from_db()
        self.assertEqual(self.contract.interaction_id, interaction.id)
        self.assertEqual(interaction.university_id, self.university.id)
        self.assertEqual(interaction.comment, "Первичный контакт")

        item = InteractionProduct.objects.get(contract=self.contract)
        self.assertEqual(item.interaction_id, interaction.id)

        responsible = Responsible.objects.get(interaction=interaction, unassigned_at__isnull=True)
        self.assertEqual(responsible.manager_id, self.manager.id)

    def test_manager_from_contract_is_not_assigned_implicitly(self) -> None:
        """ФИО менеджера из договора — только подсказка: без явного manager ответственного нет."""
        interaction = contract_attachment_service.attach_to_new_interaction(
            contract=self.contract, assigned_by=self.manager
        )

        # Проверяем, что ответственный не назначен, хотя пользователь с таким ФИО есть
        self.assertFalse(Responsible.objects.filter(interaction=interaction).exists())

    def test_explicit_manager_other_than_contract_one_is_assigned(self) -> None:
        """Явно выбранный менеджер назначается, даже если в договоре указан другой."""
        chosen = UserFactory(first_name="Пётр", last_name="Петров")

        interaction = contract_attachment_service.attach_to_new_interaction(
            contract=self.contract, assigned_by=self.manager, manager=chosen
        )

        # Проверяем назначение выбранного менеджера и автора назначения
        current = Responsible.objects.get(interaction=interaction, unassigned_at__isnull=True)
        self.assertEqual((current.manager_id, current.assigned_by_id), (chosen.id, self.manager.id))


class SuggestManagerTestCase(TestCase):
    """Подбор пользователя по ФИО менеджера из реестра."""

    def setUp(self) -> None:
        self.manager = UserFactory(first_name="Иван", last_name="Иванов")

    def test_full_name_matches_regardless_of_word_order_and_case(self) -> None:
        """draft_manager_full_name хранится «Фамилия Имя», get_full_name() — «Имя Фамилия»."""
        # Проверяем оба порядка слов, регистр и лишние пробелы
        self.assertEqual(responsible_service.suggest_manager("  иван   ИВАНОВ "), self.manager)
        self.assertEqual(responsible_service.suggest_manager("Иванов Иван"), self.manager)

    def test_unknown_or_empty_name_gives_no_suggestion(self) -> None:
        # Проверяем, что подсказки нет
        self.assertIsNone(responsible_service.suggest_manager("Несуществующий Менеджер"))
        self.assertIsNone(responsible_service.suggest_manager(""))

    def test_ambiguous_name_gives_no_suggestion(self) -> None:
        UserFactory(first_name="Иван", last_name="Иванов")  # тёзка self.manager

        # Проверяем, что при однофамильцах подсказки нет, а find_manager сообщает причину
        self.assertIsNone(responsible_service.suggest_manager("Иванов Иван"))
        with self.assertRaises(AmbiguousManagerError):
            responsible_service.find_manager("Иванов Иван")

    def test_inactive_user_is_not_suggested(self) -> None:
        self.manager.is_active = False
        self.manager.save(update_fields=["is_active"])

        # Проверяем, что неактивный пользователь не найден
        with self.assertRaises(ManagerNotFoundError):
            responsible_service.find_manager("Иванов Иван")


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
