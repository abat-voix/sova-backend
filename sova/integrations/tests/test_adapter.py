from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from sova.integrations.adapter import PermanentIntegrationError, TemporaryIntegrationError, send


@override_settings(
    INTEGRATION_SYSTEMS={"lms": {"url": "http://lms.test/events", "outbound_token": "secret"}},
    INTEGRATION_HTTP_TIMEOUT=7,
)
class IntegrationAdapterTest(SimpleTestCase):
    def test_sends_envelope_and_classifies_responses(self):
        message = Mock(system="lms", external_id="event-1", event_type="changed", correlation_id="corr", payload={"x": 1})
        message.created_at = timezone.now()
        response = Mock(status_code=204, text="")
        with patch("sova.integrations.adapter.requests.post", return_value=response) as post:
            send(message)
        self.assertEqual(post.call_args.kwargs["json"]["data"], {"x": 1})
        self.assertEqual(post.call_args.kwargs["timeout"], 7)

    def test_retryable_and_permanent_errors(self):
        message = Mock(system="lms", external_id="event-1", event_type="changed", correlation_id="corr", payload={})
        message.created_at = timezone.now()
        with patch("sova.integrations.adapter.requests.post", return_value=Mock(status_code=503, text="down")):
            with self.assertRaises(TemporaryIntegrationError):
                send(message)
        with patch("sova.integrations.adapter.requests.post", return_value=Mock(status_code=400, text="bad")):
            with self.assertRaises(PermanentIntegrationError):
                send(message)
