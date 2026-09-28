from unittest.mock import patch

from django.test import TestCase, override_settings

from sova.integrations.enum import IntegrationDirection, IntegrationStatus
from sova.catalog.models import B2CClient
from sova.integrations.models import IntegrationMapping, IntegrationMessage
from sova.integrations.tasks import process_incoming_message


@override_settings(
    INTEGRATION_SYSTEMS={"lms": {"url": "http://lms.test", "inbound_token": "in", "outbound_token": "out"}},
    INTEGRATION_MAX_ATTEMPTS=5,
)
class IntegrationTasksTest(TestCase):
    def test_unknown_event_is_ignored(self):
        message = IntegrationMessage.objects.create(
            system="lms", direction=IntegrationDirection.INCOMING, payload={"x": 1}, event_type="new.event"
        )
        process_incoming_message.run(str(message.pk))
        message.refresh_from_db()
        self.assertEqual(message.status, IntegrationStatus.IGNORED)
        self.assertIn("No handler", message.last_error)

    @patch("sova.integrations.handlers.HANDLERS", {"known.event": lambda message: None})
    def test_known_event_is_processed(self):
        message = IntegrationMessage.objects.create(
            system="lms", direction=IntegrationDirection.INCOMING, payload={}, event_type="known.event"
        )
        process_incoming_message.run(str(message.pk))
        message.refresh_from_db()
        self.assertEqual(message.status, IntegrationStatus.PROCESSED)
        self.assertEqual(message.attempts, 1)

    def test_active_mapping_parses_incoming_event(self):
        IntegrationMapping.objects.create(
            name="LMS B2C", system="lms", event_type="student.enrolled", direction=IntegrationDirection.INCOMING,
            entity="b2c_client", is_active=True,
            rules=[
                {"sourcePath": "$.name", "targetField": "full_name", "required": True, "defaultValue": None},
                {"sourcePath": "", "targetField": "kind", "required": True, "defaultValue": "individual"},
            ],
        )
        message = IntegrationMessage.objects.create(
            system="lms", direction=IntegrationDirection.INCOMING, payload={"name": "Мария"}, event_type="student.enrolled"
        )
        process_incoming_message.run(str(message.pk))
        message.refresh_from_db()
        self.assertEqual(message.status, IntegrationStatus.PROCESSED)
        self.assertEqual(B2CClient.objects.get(pk=message.result["created"][0]["id"]).full_name, "Мария")

    def test_mapping_errors_fail_message(self):
        IntegrationMapping.objects.create(
            name="LMS B2C", system="lms", event_type="student.enrolled", direction=IntegrationDirection.INCOMING,
            entity="b2c_client", is_active=True,
            rules=[
                {"sourcePath": "$.name", "targetField": "full_name", "required": True, "defaultValue": None},
                {"sourcePath": "", "targetField": "kind", "required": True, "defaultValue": "individual"},
            ],
        )
        message = IntegrationMessage.objects.create(
            system="lms", direction=IntegrationDirection.INCOMING, payload={}, event_type="student.enrolled"
        )
        process_incoming_message.run(str(message.pk))
        message.refresh_from_db()
        self.assertEqual(message.status, IntegrationStatus.FAILED)
        self.assertIn("$.name", message.last_error)
