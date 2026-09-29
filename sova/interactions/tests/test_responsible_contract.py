from django.test import TestCase

from sova.catalog.tests.factories import OrganizationFactory
from sova.core.tests.factories import UserFactory
from sova.interactions.services import responsible_service
from sova.interactions.tests.factories import ContractFactory


class SyncContractResponsiblesTestCase(TestCase):
    """Ответственные договора приводятся к переданному набору КАМов."""

    def setUp(self) -> None:
        self.contract = ContractFactory(interaction=None, organization=OrganizationFactory())
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
