from django.test import TestCase

from sova.core.tests.factories import UserFactory
from sova.messaging.exceptions import NotConversationParticipantError, SystemConversationIsReadOnlyError
from sova.messaging.services import conversation_service, message_service


class MessageServiceTestCase(TestCase):
    """Тесты отправки сообщений, отметки прочтения и подсчёта непрочитанного."""

    def test_send_creates_message_and_bumps_conversation_last_message_at(self) -> None:
        """Отправка создаёт сообщение и обновляет last_message_at беседы."""
        user_a, user_b = UserFactory(), UserFactory()
        conversation = conversation_service.get_or_create_direct(user_a, user_b)

        message = message_service.send(conversation=conversation, sender=user_a, text="Привет")

        self.assertEqual(message.text, "Привет")
        self.assertEqual(message.sender, user_a)
        conversation.refresh_from_db()
        self.assertEqual(conversation.last_message_at, message.created_at)

    def test_send_rejects_non_participant(self) -> None:
        """Отправитель, не входящий в беседу, не может в неё писать."""
        user_a, user_b, outsider = UserFactory(), UserFactory(), UserFactory()
        conversation = conversation_service.get_or_create_direct(user_a, user_b)

        with self.assertRaises(NotConversationParticipantError):
            message_service.send(conversation=conversation, sender=outsider, text="Привет")

    def test_send_rejects_system_conversation(self) -> None:
        """В системную беседу нельзя писать через пользовательскую отправку."""
        user = UserFactory()
        conversation = conversation_service.get_or_create_system(user)

        with self.assertRaises(SystemConversationIsReadOnlyError):
            message_service.send(conversation=conversation, sender=user, text="Привет")

    def test_sender_does_not_count_own_message_as_unread(self) -> None:
        """Отправитель не видит своё же сообщение как непрочитанное."""
        user_a, user_b = UserFactory(), UserFactory()
        conversation = conversation_service.get_or_create_direct(user_a, user_b)

        message_service.send(conversation=conversation, sender=user_a, text="Привет")

        self.assertEqual(message_service.unread_count(user_a), 0)
        self.assertEqual(message_service.unread_count(user_b), 1)

    def test_mark_read_resets_unread_count(self) -> None:
        """Отметка прочтения обнуляет счётчик непрочитанных сообщений беседы."""
        user_a, user_b = UserFactory(), UserFactory()
        conversation = conversation_service.get_or_create_direct(user_a, user_b)
        message_service.send(conversation=conversation, sender=user_a, text="Привет")

        message_service.mark_read(conversation=conversation, user=user_b)

        self.assertEqual(message_service.unread_count(user_b), 0)

    def test_mark_read_rejects_non_participant(self) -> None:
        """Отметить прочитанной можно только беседу, в которой участвуешь."""
        user_a, user_b, outsider = UserFactory(), UserFactory(), UserFactory()
        conversation = conversation_service.get_or_create_direct(user_a, user_b)

        with self.assertRaises(NotConversationParticipantError):
            message_service.mark_read(conversation=conversation, user=outsider)

    def test_unread_count_sums_across_conversations(self) -> None:
        """Счётчик непрочитанного суммирует сообщения по всем беседам пользователя."""
        user, other_a, other_b = UserFactory(), UserFactory(), UserFactory()
        conversation_a = conversation_service.get_or_create_direct(user, other_a)
        conversation_b = conversation_service.get_or_create_direct(user, other_b)
        message_service.send(conversation=conversation_a, sender=other_a, text="Привет 1")
        message_service.send(conversation=conversation_b, sender=other_b, text="Привет 2")

        self.assertEqual(message_service.unread_count(user), 2)
