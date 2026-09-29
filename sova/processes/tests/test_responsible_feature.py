from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import SystemRole, UserRole
from sova.core.tests.factories import UserFactory
from sova.interactions.models import Responsible
from sova.processes.models import ActionFeatureExecution
from sova.processes.tests.factories import ActionInstanceFactory
from sova.workflows.tests.factories import ActionFeatureFactory


class ResponsibleFeatureApiTestCase(APITestCase):
    """Features назначения и снятия ответственного используют текущие правила ролей."""

    def setUp(self) -> None:
        self.user = UserFactory()
        UserRole.objects.create(user=self.user, role=SystemRole.PLATFORM_ADMIN)
        self.manager = UserFactory(first_name="Анна", last_name="Смирнова")
        UserRole.objects.create(user=self.manager, role=SystemRole.KAM)
        self.client.force_authenticate(user=self.user)
        self.action_instance = ActionInstanceFactory()
        ActionFeatureFactory(
            action=self.action_instance.action,
            code="responsible.assign",
            sort_order=100,
        )
        ActionFeatureFactory(
            action=self.action_instance.action,
            code="responsible.unassign",
            sort_order=101,
        )
        self.base_url = f"/api/processes/action-instances/{self.action_instance.pk}/features"

    def test_assign_and_unassign_responsible(self) -> None:
        assign_initial = self.client.get(
            f"{self.base_url}/responsible.assign/initial/",
        )

        self.assertEqual(assign_initial.status_code, status.HTTP_200_OK)
        self.assertEqual(
            assign_initial.data["managers"],
            [{
                "id": self.manager.pk,
                "full_name": "Анна Смирнова",
                "email": self.manager.email,
                "from_registry": False,
            }],
        )

        assigned = self.client.post(
            f"{self.base_url}/responsible.assign/execute/",
            {"manager": self.manager.pk},
            format="json",
        )

        self.assertEqual(assigned.status_code, status.HTTP_200_OK, msg=assigned.data)
        responsible = Responsible.objects.get(
            interaction=self.action_instance.stage_instance.workflow_instance.interaction,
            manager=self.manager,
        )
        self.assertIsNone(responsible.unassigned_at)
        self.assertEqual(assigned.data["target"]["id"], responsible.pk)

        unassign_initial = self.client.get(
            f"{self.base_url}/responsible.unassign/initial/",
        )
        self.assertEqual(unassign_initial.status_code, status.HTTP_200_OK)
        self.assertEqual(unassign_initial.data["managers"][0]["id"], self.manager.pk)

        unassigned = self.client.post(
            f"{self.base_url}/responsible.unassign/execute/",
            {"manager": self.manager.pk},
            format="json",
        )

        self.assertEqual(unassigned.status_code, status.HTTP_200_OK, msg=unassigned.data)
        responsible.refresh_from_db()
        self.assertIsNotNone(responsible.unassigned_at)
        self.assertEqual(unassigned.data["target"]["data"]["full_name"], "Анна Смирнова")
        self.assertEqual(
            list(
                ActionFeatureExecution.objects.order_by("performed_at").values_list(
                    "feature_code_snapshot",
                    flat=True,
                ),
            ),
            ["responsible.assign", "responsible.unassign"],
        )

    def test_rejects_manager_outside_assignable_roles(self) -> None:
        observer = UserFactory()
        UserRole.objects.create(user=observer, role=SystemRole.OBSERVER)

        response = self.client.post(
            f"{self.base_url}/responsible.assign/execute/",
            {"manager": observer.pk},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Responsible.objects.filter(manager=observer).exists())
