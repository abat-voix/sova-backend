import json

from django.test import SimpleTestCase

from sova.realtime.events import build_event


class RealtimeEventTestCase(SimpleTestCase):
    def test_builds_json_compatible_versioned_envelope(self) -> None:
        event = build_event("messaging.conversation_created", {"conversation_id": "test"})

        payload = event.as_dict()
        self.assertEqual(payload["version"], 1)
        self.assertEqual(payload["type"], "messaging.conversation_created")
        json.dumps(payload)

    def test_rejects_non_json_data(self) -> None:
        with self.assertRaises(TypeError):
            build_event("test", {"value": object()})
