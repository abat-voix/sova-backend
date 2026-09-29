from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import SystemRole, UserRole
from sova.catalog.models import B2CClient
from sova.integrations.enum import IntegrationStatus
from sova.integrations.models import IntegrationMapping, IntegrationMessage


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


class IntegrationMappingProcessApiTest(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.admin = user_model.objects.create_user(username="process-admin", password="test")
        UserRole.objects.create(user=self.admin, role=SystemRole.PLATFORM_ADMIN)
        self.mapping = IntegrationMapping.objects.create(
            name="LMS B2C",
            system="lms",
            event_type="student.enrolled",
            direction="incoming",
            entity="b2c_client",
            is_active=True,
            rules=[
                {"sourcePath": "$.student.name", "targetField": "full_name", "required": True, "defaultValue": None},
                {"sourcePath": "$.student.mail", "targetField": "email", "required": False, "defaultValue": None},
                {"sourcePath": "$.student.phone", "targetField": "phone", "required": False, "defaultValue": None},
            ],
        )
        self.url = reverse("integrations:mapping-process", args=[self.mapping.pk])

    def test_payload_is_parsed_into_crm_entity(self):
        self.client.force_authenticate(self.admin)
        payload = {"student": {"name": "Иван Петров", "mail": "ivan@example.com"}}
        response = self.client.post(self.url, {"payload": payload}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], IntegrationStatus.PROCESSED)
        self.assertEqual(response.data["errors"], [])
        self.assertEqual(response.data["warnings"], ["Путь не найден: $.student.phone"])
        client = B2CClient.objects.get(pk=response.data["created"][0]["id"])
        self.assertEqual((client.full_name, client.email), ("Иван Петров", "ivan@example.com"))
        message = IntegrationMessage.objects.get(pk=response.data["id"])
        self.assertEqual(message.mapping, self.mapping)
        self.assertEqual(message.payload, payload)

    def test_missing_required_value_fails_without_creating_entity(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(self.url, {"payload": {"student": {}}}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], IntegrationStatus.FAILED)
        self.assertEqual(response.data["created"], [])
        self.assertEqual(response.data["errors"], ["Отсутствует обязательное значение: $.student.name"])
        self.assertFalse(B2CClient.objects.exists())
        self.assertEqual(IntegrationMessage.objects.get().status, IntegrationStatus.FAILED)

    def test_entity_validation_errors_are_returned(self):
        self.client.force_authenticate(self.admin)
        payload = {"student": {"name": "Иван", "mail": "not-an-email"}}
        response = self.client.post(self.url, {"payload": payload}, format="json")
        self.assertEqual(response.data["status"], IntegrationStatus.FAILED)
        self.assertTrue(response.data["errors"])
        self.assertFalse(B2CClient.objects.exists())

    def test_payload_must_be_object_or_array(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(self.url, {"payload": "text"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(IntegrationMessage.objects.exists())

    def test_outgoing_mapping_is_rejected(self):
        self.client.force_authenticate(self.admin)
        self.mapping.direction = "outgoing"
        self.mapping.save(update_fields=["direction"])
        response = self.client.post(self.url, {"payload": {}}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "mapping_not_incoming")

    def test_regular_user_cannot_process(self):
        self.client.force_authenticate(get_user_model().objects.create_user(username="plain", password="test"))
        response = self.client.post(self.url, {"payload": {}}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_metadata_marks_fields_by_incoming_writability(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get(reverse("integrations:entity-metadata"))
        by_code = {item["code"]: {field["name"]: field for field in item["fields"]} for item in response.data}
        self.assertFalse(by_code["interaction"]["organization"]["read_only"])
        self.assertTrue(by_code["organization"]["has_interactions"]["read_only"])
        self.assertTrue(all(field["read_only"] for field in by_code["workflow_instance"].values()))
