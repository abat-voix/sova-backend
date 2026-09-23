from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import SystemRole, UserRole
from sova.core.tests.factories import UserFactory
from sova.workflows.models import Workflow
from sova.workflows.tests.factories import WorkflowFactory


class WorkflowPermissionTests(APITestCase):
    """Role and ownership rules for workflow administration."""

    def setUp(self) -> None:
        self.head = UserFactory()
        UserRole.objects.create(user=self.head, role=SystemRole.HEAD)
        self.other_head = UserFactory()
        UserRole.objects.create(user=self.other_head, role=SystemRole.HEAD)
        self.kam = UserFactory()
        UserRole.objects.create(user=self.kam, role=SystemRole.KAM)
        self.admin = UserFactory()
        UserRole.objects.create(user=self.admin, role=SystemRole.PLATFORM_ADMIN)
        self.owned = WorkflowFactory(created_by=self.head)
        self.foreign = WorkflowFactory(created_by=self.other_head)

    def url(self, workflow: Workflow) -> str:
        return f"/api/workflows/workflows/{workflow.pk}/"

    def test_head_can_list_all_workflows(self) -> None:
        self.client.force_authenticate(self.head)
        response = self.client.get("/api/workflows/workflows/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)

    def test_head_can_edit_only_owned_workflow(self) -> None:
        self.client.force_authenticate(self.head)
        own_response = self.client.patch(
            self.url(self.owned), {"name": "Изменён"}, format="json"
        )
        foreign_response = self.client.patch(
            self.url(self.foreign), {"name": "Нельзя"}, format="json"
        )

        self.assertEqual(own_response.status_code, status.HTTP_200_OK)
        self.assertEqual(foreign_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_kam_cannot_access_workflow_api(self) -> None:
        self.client.force_authenticate(self.kam)
        response = self.client.get("/api/workflows/workflows/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_platform_admin_can_edit_foreign_workflow(self) -> None:
        self.client.force_authenticate(self.admin)
        response = self.client.patch(
            self.url(self.foreign), {"name": "Изменён администратором"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
