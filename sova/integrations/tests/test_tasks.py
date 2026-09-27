from unittest.mock import patch

from django.test import TestCase, override_settings

from sova.integrations.enum import IntegrationDirection, IntegrationStatus
from sova.integrations.models import IntegrationMessage
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

    @patch("sova.integrations.tasks.HANDLERS", {"known.event": lambda message: None})
    def test_known_event_is_processed(self):
        message = IntegrationMessage.objects.create(
            system="lms", direction=IntegrationDirection.INCOMING, payload={}, event_type="known.event"
        )
        process_incoming_message.run(str(message.pk))
        message.refresh_from_db()
        self.assertEqual(message.status, IntegrationStatus.PROCESSED)
        self.assertEqual(message.attempts, 1)
