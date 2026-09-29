from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from sova.catalog.tests.factories import OrganizationFactory
from sova.core.tests.factories import UserFactory
from sova.interactions.models import Responsible
from sova.interactions.tests.factories import ContractFactory


class ResponsibleOwnerTestCase(TestCase):
    """Назначение принадлежит взаимодействию или договору; КАМ не дублируется на договоре."""

    def setUp(self) -> None:
        self.contract = ContractFactory(interaction=None, organization=OrganizationFactory())
        self.manager = UserFactory()

    def test_contract_responsible_without_interaction_is_saved(self) -> None:
        responsible = Responsible.objects.create(contract=self.contract, manager=self.manager)

        # Проверяем, что назначение договора сохранено без взаимодействия
        self.assertIsNone(responsible.interaction_id)
        self.assertEqual(list(self.contract.responsibles.all()), [responsible])

    def test_record_without_owner_is_rejected(self) -> None:
        # Проверяем ограничение responsible_has_owner
        with self.assertRaises(IntegrityError), transaction.atomic():
            Responsible.objects.create(manager=self.manager)

    def test_same_manager_twice_active_on_contract_is_rejected(self) -> None:
        Responsible.objects.create(contract=self.contract, manager=self.manager)

        # Проверяем ограничение one_active_responsible_per_contract
        with self.assertRaises(IntegrityError), transaction.atomic():
            Responsible.objects.create(contract=self.contract, manager=self.manager)

    def test_closed_record_does_not_block_new_one(self) -> None:
        Responsible.objects.create(contract=self.contract, manager=self.manager, unassigned_at=timezone.now())

        Responsible.objects.create(contract=self.contract, manager=self.manager)

        # Проверяем, что закрытая запись не мешает новому назначению
        self.assertEqual(self.contract.responsibles.count(), 2)
