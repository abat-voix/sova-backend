from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase

from sova.catalog.tests.factories import UniversityFactory
from sova.core.tests.factories import UserFactory
from sova.interactions.exceptions import AmbiguousManagerError, ManagerNotFoundError
from sova.interactions.models import InteractionProduct, Responsible
from sova.interactions.services import responsible_service
from sova.interactions.services.contract_attachment import contract_attachment_service
from sova.interactions.tests.factories import ContractFactory, InteractionFactory, InteractionProductFactory
from sova.notifications.enum import NotificationChannel


class AttachToNewInteractionTestCase(TestCase):
    """Привязка headless-договора создаёт Interaction и перекладывает на него безголовые записи."""

    def setUp(self) -> None:
        self.university = UniversityFactory()
        self.manager = UserFactory(first_name="Иван", last_name="Иванов")
        self.contract = ContractFactory(
            interaction=None,
            university=self.university,
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

    def test_contract_responsibles_move_to_interaction(self) -> None:
        kam = UserFactory()
        responsible_service.sync_contract_responsibles(contract=self.contract, managers=[kam], assigned_by=None)

        interaction = contract_attachment_service.attach_to_new_interaction(
            contract=self.contract, assigned_by=self.manager
        )

        # Проверяем: КАМ договора — действующий ответственный взаимодействия, назначил привязавший
        current = Responsible.objects.get(interaction=interaction, unassigned_at__isnull=True)
        self.assertEqual((current.manager_id, current.assigned_by_id), (kam.pk, self.manager.pk))

    @patch("sova.notifications.services.event_notification.send_event_notification")
    def test_explicit_manager_equal_to_contract_kam_is_not_duplicated(self, task) -> None:
        responsible_service.sync_contract_responsibles(
            contract=self.contract, managers=[self.manager], assigned_by=None
        )
        head = UserFactory()

        with self.captureOnCommitCallbacks(execute=True):
            interaction = contract_attachment_service.attach_to_new_interaction(
                contract=self.contract, assigned_by=head, manager=self.manager
            )

        # Проверяем: одна запись и одно уведомление
        self.assertEqual(Responsible.objects.filter(interaction=interaction).count(), 1)
        system_calls = [
            item for item in task.delay.call_args_list if item.kwargs["channels"] == [NotificationChannel.SYSTEM]
        ]
        self.assertEqual(len(system_calls), 1)

    def test_explicit_manager_is_added_to_contract_kams(self) -> None:
        kam = UserFactory()
        responsible_service.sync_contract_responsibles(contract=self.contract, managers=[kam], assigned_by=None)
        chosen = UserFactory(first_name="Пётр", last_name="Петров")

        interaction = contract_attachment_service.attach_to_new_interaction(
            contract=self.contract, assigned_by=self.manager, manager=chosen
        )

        # Проверяем: у взаимодействия оба КАМа — с договора и выбранный явно
        current = set(
            Responsible.objects.filter(interaction=interaction, unassigned_at__isnull=True).values_list(
                "manager_id", flat=True
            )
        )
        self.assertEqual(current, {kam.pk, chosen.pk})


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
