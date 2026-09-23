from django.test import TestCase

from sova.core.tests.factories import UserFactory
from sova.messaging.enum import ConversationKind
from sova.messaging.models import Conversation
from sova.messaging.services import conversation_service


class ConversationServiceTestCase(TestCase):
    """Тесты создания и дедупликации бесед."""

    def test_get_or_create_direct_creates_conversation_with_both_participants(self) -> None:
        """Первое обращение создаёт личную беседу с обоими участниками."""
        user_a, user_b = UserFactory(), UserFactory()

        conversation = conversation_service.get_or_create_direct(user_a, user_b)

        self.assertEqual(conversation.kind, ConversationKind.DIRECT)
        participant_ids = set(conversation.participants.values_list("user_id", flat=True))
        self.assertEqual(participant_ids, {user_a.pk, user_b.pk})

    def test_get_or_create_direct_is_idempotent_regardless_of_argument_order(self) -> None:
        """Повторное обращение (в любом порядке аргументов) не создаёт дубль беседы."""
        user_a, user_b = UserFactory(), UserFactory()

        first = conversation_service.get_or_create_direct(user_a, user_b)
        second = conversation_service.get_or_create_direct(user_b, user_a)

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Conversation.objects.filter(kind=ConversationKind.DIRECT).count(), 1)

    def test_get_or_create_direct_rejects_same_user(self) -> None:
        """Личная беседа требует двух разных пользователей."""
        user = UserFactory()

        with self.assertRaises(ValueError):
            conversation_service.get_or_create_direct(user, user)

    def test_get_or_create_system_is_idempotent_per_user(self) -> None:
        """У пользователя ровно одна системная беседа при повторных обращениях."""
        user = UserFactory()

        first = conversation_service.get_or_create_system(user)
        second = conversation_service.get_or_create_system(user)

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(first.kind, ConversationKind.SYSTEM)
        self.assertEqual(list(first.participants.values_list("user_id", flat=True)), [user.pk])

    def test_different_users_get_different_system_conversations(self) -> None:
        """Системные беседы разных пользователей не пересекаются."""
        user_a, user_b = UserFactory(), UserFactory()

        conversation_a = conversation_service.get_or_create_system(user_a)
        conversation_b = conversation_service.get_or_create_system(user_b)

        self.assertNotEqual(conversation_a.pk, conversation_b.pk)
