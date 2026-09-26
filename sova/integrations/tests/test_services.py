from unittest.mock import patch

from django.test import TestCase, override_settings

from sova.integrations.enum import IntegrationDirection
from sova.integrations.models import IntegrationMessage
from sova.integrations.services import enqueue_outgoing, receive_message


@override_settings(
    INTEGRATION_SYSTEMS={"lms": {"url": "http://lms.test", "inbound_token": "in", "outbound_token": "out"}}
)
class IntegrationServicesTest(TestCase):
    @patch("sova.integrations.services._schedule")
    def test_receive_preserves_payload_and_deduplicates(self, schedule):
        payload = {"known": 1, "future": {"values": [True, None]}}
        with self.captureOnCommitCallbacks(execute=True):
            first = receive_message(system="lms", event_type="student.enrolled", payload=payload, external_id="x")
        second = receive_message(system="lms", event_type="student.enrolled", payload={"different": True}, external_id="x")
        self.assertFalse(first.duplicate)
        self.assertTrue(second.duplicate)
        self.assertEqual(first.message.payload, payload)
        self.assertEqual(schedule.call_count, 1)

    @patch("sova.integrations.services._schedule")
    def test_outgoing_is_created_without_http(self, schedule):
        with self.captureOnCommitCallbacks(execute=True):
            message = enqueue_outgoing(
                system="lms", event_type="workflow.status.changed", payload={"status": "done"}, external_id="workflow-1"
            )
        self.assertEqual(message.direction, IntegrationDirection.OUTGOING)
        self.assertEqual(IntegrationMessage.objects.get(pk=message.pk).payload, {"status": "done"})
        schedule.assert_called_once()
