from django.test import TestCase

from sova.core.tests.factories import UserFactory
from sova.messaging.services import conversation_service, message_service
from sova.messaging.services.system_messages import send_system_message


class SendSystemMessageTestCase(TestCase):
    """Тесты сервисной точки входа для системных сообщений."""

    def test_sends_to_each_user_own_system_conversation(self) -> None:
        """Каждый получатель получает сообщение в свою системную беседу."""
        user_a, user_b = UserFactory(), UserFactory()

        messages = send_system_message([user_a, user_b], text="Ваша задача назначена")

        self.assertEqual(len(messages), 2)
        for user, message in zip((user_a, user_b), messages, strict=True):
            self.assertIsNone(message.sender)
            self.assertEqual(message.conversation, conversation_service.get_or_create_system(user))

    def test_system_message_counts_as_unread(self) -> None:
        """Системное сообщение увеличивает счётчик непрочитанного получателя."""
        user = UserFactory()

        send_system_message([user], text="Добро пожаловать")

        self.assertEqual(message_service.unread_count(user), 1)

    def test_repeated_calls_reuse_same_system_conversation(self) -> None:
        """Повторная отправка не создаёт вторую системную беседу пользователя."""
        user = UserFactory()

        send_system_message([user], text="Первое")
        send_system_message([user], text="Второе")

        conversation = conversation_service.get_or_create_system(user)
        self.assertEqual(conversation.messages.count(), 2)
