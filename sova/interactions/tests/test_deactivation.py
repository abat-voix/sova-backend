from unittest.mock import patch

from django.test import TestCase

from accounts.models import SystemRole, UserRole
from accounts.services import account_service
from sova.catalog.tests.factories import OrganizationFactory
from sova.core.tests.factories import UserFactory
from sova.interactions.models import Responsible
from sova.interactions.services import responsible_service
from sova.interactions.tests.factories import ContractFactory, InteractionFactory
from sova.processes.enum import ActionInstanceStatus
from sova.processes.tests.factories import ActionInstanceFactory


@patch("sova.notifications.services.event_notification.send_event_notification")
class DeactivationReleasesResponsibilitiesTestCase(TestCase):
    """Деактивация снимает пользователя со всех взаимодействий, его открытые задачи уходят в пул."""

    def setUp(self) -> None:
        """КАМ — ответственный на двух взаимодействиях, на одном вместе с другим КАМом."""
        self.kam = UserFactory()
        UserRole.objects.create(user=self.kam, role=SystemRole.KAM)
        self.colleague = UserFactory()
        UserRole.objects.create(user=self.colleague, role=SystemRole.KAM)
        self.alone = InteractionFactory()
        self.shared = InteractionFactory()
        for interaction in (self.alone, self.shared):
            responsible_service.assign(interaction=interaction, manager=self.kam, assigned_by=None)
        responsible_service.assign(interaction=self.shared, manager=self.colleague, assigned_by=None)

    def test_deactivation_closes_all_active_assignments(self, task) -> None:
        """После деактивации у КАМа нет действующих назначений, коллега остаётся."""
        account_service.deactivate(user=self.kam, actor=None)

        # Проверяем назначения КАМа и коллеги
        self.assertFalse(Responsible.objects.filter(manager=self.kam, unassigned_at__isnull=True).exists())
        self.assertTrue(
            Responsible.objects.filter(manager=self.colleague, interaction=self.shared, unassigned_at__isnull=True)
            .exists(),
        )

    def test_deactivation_returns_open_actions_to_pool(self, task) -> None:
        """Открытые задачи КАМа уходят в пул, завершённые остаются за ним."""
        open_action = ActionInstanceFactory(
            stage_instance__workflow_instance__interaction=self.alone,
            responsible=self.kam,
        )
        done_action = ActionInstanceFactory(
            stage_instance__workflow_instance__interaction=self.alone,
            responsible=self.kam,
            status=ActionInstanceStatus.COMPLETED,
        )

        account_service.deactivate(user=self.kam, actor=None)

        open_action.refresh_from_db()
        done_action.refresh_from_db()
        # Проверяем пул и историю
        self.assertIsNone(open_action.responsible_id)
        self.assertEqual(done_action.responsible_id, self.kam.pk)

    def test_deactivation_closes_headless_contract_assignments(self, task) -> None:
        """Назначение на headless-договор из реестра закрывается вместе с назначениями на взаимодействия."""
        contract = ContractFactory(interaction=None, organization=OrganizationFactory())
        responsible_service.sync_contract_responsibles(contract=contract, managers=[self.kam], assigned_by=None)

        account_service.deactivate(user=self.kam, actor=None)

        self.assertFalse(Responsible.objects.filter(manager=self.kam, unassigned_at__isnull=True).exists())
        self.assertTrue(Responsible.objects.filter(manager=self.kam, contract=contract).exists())

    def test_history_is_kept(self, task) -> None:
        """Назначения закрываются, а не удаляются."""
        account_service.deactivate(user=self.kam, actor=None)

        self.assertEqual(Responsible.objects.filter(manager=self.kam).count(), 2)
