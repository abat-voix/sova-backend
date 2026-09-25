from unittest.mock import patch
from uuid import uuid4

from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from sova.integrations.models import IntegrationMessage


@override_settings(
    INTEGRATION_SYSTEMS={
        "lms": {"url": "http://lms.test/events", "inbound_token": "secret", "outbound_token": "out"},
        "cms": {"url": "", "inbound_token": "cms-secret", "outbound_token": ""},
    },
    CELERY_TASK_ALWAYS_EAGER=False,
)
class IntegrationEventsApiTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = reverse("integrations:events", kwargs={"system_code": "lms"})

    @patch("sova.integrations.api.views.receive_message")
    def test_accepts_arbitrary_object_and_authenticates(self, receive):
        message = IntegrationMessage(id=uuid4(), status="pending")
        receive.return_value.message = message
        receive.return_value.duplicate = False
        payload = {"student_id": "123", "unknown": {"nested": [1, 2]}}
        response = self.client.post(
            self.url,
            payload,
            format="json",
            HTTP_AUTHORIZATION="Bearer secret",
            HTTP_X_EVENT_ID="event-1",
        )
        self.assertEqual(response.status_code, 202)
        receive.assert_called_once()
        self.assertEqual(receive.call_args.kwargs["payload"], payload)

    def test_duplicate_is_idempotent(self):
        body = {"eventType": "unknown.event", "custom": "value"}
        first = self.client.post(
            self.url, body, format="json", HTTP_AUTHORIZATION="Bearer secret", HTTP_X_EVENT_ID="event-1"
        )
        second = self.client.post(
            self.url, body, format="json", HTTP_AUTHORIZATION="Bearer secret", HTTP_X_EVENT_ID="event-1"
        )
        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.data["duplicate"])
        self.assertEqual(IntegrationMessage.objects.count(), 1)

    def test_rejects_invalid_token_and_non_object(self):
        response = self.client.post(self.url, {}, format="json", HTTP_AUTHORIZATION="Bearer wrong")
        self.assertEqual(response.status_code, 401)
        response = self.client.post(self.url, [], format="json", HTTP_AUTHORIZATION="Bearer secret")
        self.assertEqual(response.status_code, 400)
