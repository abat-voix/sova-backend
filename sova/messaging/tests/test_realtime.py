from unittest.mock import patch

from django.test import TestCase

from sova.core.tests.factories import UserFactory
from sova.messaging.presentation import message_representation
from sova.messaging.services import conversation_service, message_service


class MessagingRealtimeTestCase(TestCase):
    def test_message_is_published_only_after_commit_to_all_participants(self) -> None:
        user_a, user_b = UserFactory(), UserFactory()
        conversation = conversation_service.get_or_create_direct(user_a, user_b)

        with patch("sova.messaging.realtime.async_to_sync") as async_to_sync_mock:
            sender = async_to_sync_mock.return_value
            with self.captureOnCommitCallbacks(execute=False) as callbacks:
                message = message_service.send(conversation, user_a, "Привет")
            sender.assert_not_called()
            self.assertEqual(len(callbacks), 1)
            callbacks[0]()

        self.assertEqual(sender.call_count, 2)
        groups = {call.args[0] for call in sender.call_args_list}
        self.assertEqual(groups, {f"user.{user_a.pk}", f"user.{user_b.pk}"})
        envelope = sender.call_args.args[1]["event"]
        self.assertEqual(envelope["data"]["message"], message_representation(message))

    def test_read_event_targets_only_reader_and_uses_saved_timestamp(self) -> None:
        user_a, user_b = UserFactory(), UserFactory()
        conversation = conversation_service.get_or_create_direct(user_a, user_b)

        with patch("sova.messaging.realtime.async_to_sync") as async_to_sync_mock:
            sender = async_to_sync_mock.return_value
            with self.captureOnCommitCallbacks(execute=True):
                message_service.mark_read(conversation, user_b)

        self.assertEqual(sender.call_count, 1)
        self.assertEqual(sender.call_args.args[0], f"user.{user_b.pk}")
        event = sender.call_args.args[1]["event"]
        participant = conversation.participants.get(user=user_b)
        self.assertEqual(event["data"]["read_at"], participant.last_read_at.isoformat(timespec="milliseconds").replace("+00:00", "Z"))
