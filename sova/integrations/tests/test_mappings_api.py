from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import SystemRole, UserRole
from sova.integrations.models import IntegrationMapping


class IntegrationMappingsApiTest(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.admin = user_model.objects.create_user(username="mapping-admin", password="test")
        UserRole.objects.create(user=self.admin, role=SystemRole.PLATFORM_ADMIN)
        self.user = user_model.objects.create_user(username="mapping-user", password="test")

    def test_regular_user_cannot_access_configuration(self):
        self.client.force_authenticate(self.user)
        response = self.client.get(reverse("integrations:mapping-list"))
        self.assertEqual(response.status_code, 403)

    def test_admin_can_read_serializer_metadata(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get(reverse("integrations:entity-metadata"))
        self.assertEqual(response.status_code, 200)
        workflow = next(item for item in response.data if item["code"] == "workflow_instance")
        self.assertIn("status", {field["name"] for field in workflow["fields"]})

    def test_crud_validates_registered_crm_fields(self):
        self.client.force_authenticate(self.admin)
        payload = {
            "name": "LMS enrollment",
            "system": "lms",
            "eventType": "student.enrolled",
            "direction": "incoming",
            "entity": "b2c_client",
            "isActive": True,
            "rules": [{"sourcePath": "$.mail", "targetField": "email", "required": True, "defaultValue": None}],
        }
        response = self.client.post(reverse("integrations:mapping-list"), payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        mapping = IntegrationMapping.objects.get()
        self.assertEqual(mapping.rules[0]["targetField"], "email")

        invalid = {**payload, "rules": [{**payload["rules"][0], "targetField": "missing"}]}
        response = self.client.post(reverse("integrations:mapping-list"), invalid, format="json")
        self.assertEqual(response.status_code, 400)

    def test_preview_reports_missing_required_value(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            reverse("integrations:mapping-preview"),
            {
                "entity": "b2c_client",
                "direction": "incoming",
                "rules": [{"sourcePath": "$.mail", "targetField": "email", "required": True}],
                "payload": {},
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["result"], {})
        self.assertTrue(response.data["errors"])
