from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import SystemRole, UserRole
from sova.catalog.tests.factories import OrganizationFactory
from sova.core.tests.factories import UserFactory
from sova.interactions.exceptions import AmbiguousManagerError, ManagerNotFoundError
from sova.interactions.models import InteractionProduct, Responsible
from sova.interactions.services import responsible_service
from sova.interactions.services.contract_attachment import contract_attachment_service
from sova.interactions.tests.factories import ContractFactory, InteractionFactory, InteractionProductFactory


class AttachToNewInteractionTestCase(TestCase):
    """Привязка headless-договора создаёт Interaction и перекладывает на него безголовые записи."""

    def setUp(self) -> None:
        self.organization = OrganizationFactory()
        self.kam = self._user(SystemRole.KAM)
        self.registry_kam = self._user(SystemRole.KAM)
        self.contract = ContractFactory(
            interaction=None,
            organization=self.organization,
            draft_comment="Первичный контакт",
        )
        InteractionProductFactory(contract=self.contract, interaction=None)
        responsible_service.sync_contract_responsibles(
            contract=self.contract, managers=[self.registry_kam], assigned_by=None
        )

    @staticmethod
    def _user(role: str):
        user = UserFactory()
        UserRole.objects.create(user=user, role=role)
        return user

    @staticmethod
    def _current(interaction) -> set[int]:
        return set(
            Responsible.objects.filter(interaction=interaction, unassigned_at__isnull=True).values_list(
                "manager_id", flat=True
            )
        )

    def test_creates_interaction_and_attaches_headless_records(self) -> None:
        interaction = contract_attachment_service.attach_to_new_interaction(contract=self.contract, author=self.kam)

        self.contract.refresh_from_db()
        self.assertEqual(self.contract.interaction_id, interaction.id)
        self.assertEqual(interaction.organization_id, self.organization.id)
        self.assertEqual(interaction.comment, "Первичный контакт")

        item = InteractionProduct.objects.get(contract=self.contract)
        self.assertEqual(item.interaction_id, interaction.id)

    def test_kam_author_becomes_the_only_responsible(self) -> None:
        interaction = contract_attachment_service.attach_to_new_interaction(contract=self.contract, author=self.kam)

        # Проверяем: ответственный — только автор-КАМ, КАМ из реестра не перешёл
        self.assertEqual(self._current(interaction), {self.kam.pk})

    def test_head_author_leaves_interaction_unassigned(self) -> None:
        interaction = contract_attachment_service.attach_to_new_interaction(
            contract=self.contract, author=self._user(SystemRole.HEAD)
        )

        # Проверяем: как при обычном создании — взаимодействие ничьё
        self.assertEqual(self._current(interaction), set())

    def test_registry_kams_stay_on_contract(self) -> None:
        contract_attachment_service.attach_to_new_interaction(contract=self.contract, author=self.kam)

        # Проверяем: назначение из реестра осталось на договоре действующим, без взаимодействия
        registry = Responsible.objects.get(contract=self.contract, manager=self.registry_kam)
        self.assertEqual((registry.interaction_id, registry.unassigned_at), (None, None))


class FindManagerTestCase(TestCase):
    """Поиск пользователя по ФИО менеджера из реестра."""

    def setUp(self) -> None:
        self.manager = UserFactory(first_name="Иван", last_name="Иванов")

    def test_full_name_matches_regardless_of_word_order_and_case(self) -> None:
        """В файле ФИО «Фамилия Имя», get_full_name() — «Имя Фамилия»."""
        # Проверяем оба порядка слов, регистр и лишние пробелы
        self.assertEqual(responsible_service.find_manager("  иван   ИВАНОВ "), self.manager)
        self.assertEqual(responsible_service.find_manager("Иванов Иван"), self.manager)

    def test_unknown_name_raises(self) -> None:
        # Проверяем, что неизвестное ФИО не найдено
        with self.assertRaises(ManagerNotFoundError):
            responsible_service.find_manager("Несуществующий Менеджер")

    def test_ambiguous_name_raises(self) -> None:
        UserFactory(first_name="Иван", last_name="Иванов")  # тёзка self.manager

        # Проверяем, что при однофамильцах find_manager сообщает причину
        with self.assertRaises(AmbiguousManagerError):
            responsible_service.find_manager("Иванов Иван")

    def test_inactive_user_is_not_found(self) -> None:
        self.manager.is_active = False
        self.manager.save(update_fields=["is_active"])

        # Проверяем, что неактивный пользователь не найден
        with self.assertRaises(ManagerNotFoundError):
            responsible_service.find_manager("Иванов Иван")


class AttachToExistingInteractionTestCase(TestCase):
    """Привязка договора к уже существующему Interaction не трогает comment/Responsible."""

    def test_attaches_products_without_touching_comment_or_responsible(self) -> None:
        interaction = InteractionFactory(organization=OrganizationFactory(), comment="Исходный комментарий")
        contract = ContractFactory(
            interaction=None,
            organization=interaction.organization,
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
        interaction = InteractionFactory(organization=OrganizationFactory())
        contract = ContractFactory(interaction=None, organization=OrganizationFactory())

        with self.assertRaises(ValidationError):
            contract_attachment_service.attach_to_existing_interaction(contract=contract, interaction=interaction)

        contract.refresh_from_db()
        self.assertIsNone(contract.interaction_id)
