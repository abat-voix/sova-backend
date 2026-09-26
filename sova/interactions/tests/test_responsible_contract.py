from unittest.mock import patch

from django.test import TestCase

from sova.catalog.tests.factories import UniversityFactory
from sova.core.tests.factories import UserFactory
from sova.interactions.models import Interaction, Responsible
from sova.interactions.services import responsible_service
from sova.interactions.tests.factories import ContractFactory
from sova.notifications.enum import NotificationChannel


class SyncContractResponsiblesTestCase(TestCase):
    """Ответственные договора приводятся к переданному набору КАМов."""

    def setUp(self) -> None:
        self.contract = ContractFactory(interaction=None, university=UniversityFactory())
        self.ivanov = UserFactory()
        self.petrov = UserFactory()
        self.importer = UserFactory()

    def current(self) -> set[int]:
        return set(
            self.contract.responsibles.filter(unassigned_at__isnull=True).values_list("manager_id", flat=True)
        )

    def test_assigns_missing_and_closes_absent(self) -> None:
        responsible_service.sync_contract_responsibles(
            contract=self.contract, managers=[self.ivanov, self.petrov], assigned_by=self.importer
        )
        responsible_service.sync_contract_responsibles(
            contract=self.contract, managers=[self.ivanov], assigned_by=self.importer
        )

        # Проверяем: Иванов остался, Петров снят и остался в истории
        self.assertEqual(self.current(), {self.ivanov.pk})
        closed = self.contract.responsibles.get(manager=self.petrov)
        self.assertIsNotNone(closed.unassigned_at)
        # Проверяем автора назначения и отсутствие взаимодействия
        kept = self.contract.responsibles.get(manager=self.ivanov)
        self.assertEqual((kept.assigned_by_id, kept.interaction_id), (self.importer.pk, None))

    def test_same_set_again_keeps_history(self) -> None:
        responsible_service.sync_contract_responsibles(
            contract=self.contract, managers=[self.ivanov], assigned_by=self.importer
        )
        responsible_service.sync_contract_responsibles(
            contract=self.contract, managers=[self.ivanov], assigned_by=self.importer
        )

        # Проверяем, что повторная синхронизация не плодит записи
        self.assertEqual(self.contract.responsibles.count(), 1)

    def test_duplicate_manager_in_input_is_assigned_once(self) -> None:
        responsible_service.sync_contract_responsibles(
            contract=self.contract, managers=[self.ivanov, self.ivanov], assigned_by=None
        )

        # Проверяем одно назначение
        self.assertEqual(self.contract.responsibles.count(), 1)

    def test_empty_set_closes_all(self) -> None:
        responsible_service.sync_contract_responsibles(contract=self.contract, managers=[self.ivanov], assigned_by=None)
        responsible_service.sync_contract_responsibles(contract=self.contract, managers=[], assigned_by=None)

        # Проверяем, что действующих не осталось
        self.assertEqual(self.current(), set())


@patch("sova.notifications.services.event_notification.send_event_notification")
class TransferFromContractTestCase(TestCase):
    """Действующие ответственные договора переходят на взаимодействие."""

    def setUp(self) -> None:
        self.university = UniversityFactory()
        self.contract = ContractFactory(interaction=None, university=self.university)
        self.interaction = Interaction.objects.create(university=self.university)
        self.kam = UserFactory()
        self.gone = UserFactory()
        self.importer = UserFactory()
        self.head = UserFactory()
        responsible_service.sync_contract_responsibles(
            contract=self.contract, managers=[self.kam, self.gone], assigned_by=self.importer
        )
        responsible_service.sync_contract_responsibles(
            contract=self.contract, managers=[self.kam], assigned_by=self.importer
        )

    def transfer(self, assigned_by) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            responsible_service.transfer_from_contract(
                contract=self.contract, interaction=self.interaction, assigned_by=assigned_by
            )

    def test_active_records_move_with_new_assigner_and_date(self, task) -> None:
        before = Responsible.objects.get(contract=self.contract, manager=self.kam)

        self.transfer(assigned_by=self.head)

        # Проверяем: та же запись, взаимодействие проставлено, договор сохранён, автор и дата перезаписаны
        moved = Responsible.objects.get(pk=before.pk)
        self.assertEqual((moved.interaction_id, moved.contract_id), (self.interaction.pk, self.contract.pk))
        self.assertEqual(moved.assigned_by_id, self.head.pk)
        self.assertGreater(moved.assigned_at, before.assigned_at)

    def test_closed_records_stay_on_contract(self, task) -> None:
        self.transfer(assigned_by=self.head)

        # Проверяем, что снятый при синхронизации КАМ не перешёл
        gone = Responsible.objects.get(contract=self.contract, manager=self.gone)
        self.assertIsNone(gone.interaction_id)

    def test_moved_kam_is_notified(self, task) -> None:
        self.transfer(assigned_by=self.head)

        # Проверяем уведомление перешедшему КАМу
        system_calls = [
            item.kwargs for item in task.delay.call_args_list if item.kwargs["channels"] == [NotificationChannel.SYSTEM]
        ]
        self.assertEqual([call["user_ids"] for call in system_calls], [[self.kam.pk]])
        self.assertEqual(
            system_calls[0]["text"],
            f"{self.kam.get_full_name()}({self.kam.email}), Вас назначили КАМом — {self.university.name}",
        )

    def test_self_assignment_is_not_notified(self, task) -> None:
        self.transfer(assigned_by=self.kam)

        # Проверяем, что привязавший договор КАМ сам себе уведомление не получает
        self.assertFalse(task.delay.called)
