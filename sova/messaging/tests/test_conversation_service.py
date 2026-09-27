from django.test import TestCase

from accounts.models import SystemRole, UserRole
from sova.core.tests.factories import UserFactory
from sova.interactions.tests.factories import InteractionFactory
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

    def test_get_or_create_interaction_creates_conversation_with_actor_and_users(self) -> None:
        """Первое обращение создаёт чат Взаимодействия с автором и переданными участниками."""
        interaction = InteractionFactory()
        actor, invited = UserFactory(), UserFactory()

        conversation, created = conversation_service.get_or_create_interaction(
            interaction=interaction,
            actor=actor,
            users=[invited],
        )

        self.assertTrue(created)
        self.assertEqual(conversation.kind, ConversationKind.INTERACTION)
        self.assertEqual(conversation.interaction_id, interaction.pk)
        self.assertEqual(conversation.created_by_id, actor.pk)
        self.assertEqual(
            set(conversation.participants.values_list("user_id", flat=True)),
            {actor.pk, invited.pk},
        )

    def test_get_or_create_interaction_is_idempotent_per_interaction(self) -> None:
        """Повторное обращение возвращает тот же чат и не создаёт дубль."""
        interaction = InteractionFactory()
        actor = UserFactory()

        first, first_created = conversation_service.get_or_create_interaction(interaction, actor)
        second, second_created = conversation_service.get_or_create_interaction(interaction, actor)

        self.assertEqual(first.pk, second.pk)
        self.assertTrue(first_created)
        self.assertFalse(second_created)
        self.assertEqual(Conversation.objects.filter(kind=ConversationKind.INTERACTION).count(), 1)

    def test_get_or_create_interaction_does_not_add_users_from_repeat_request(self) -> None:
        """Повторный вызов с новыми participant_ids не меняет состав уже созданного чата."""
        interaction = InteractionFactory()
        actor, invited_first, invited_second = UserFactory(), UserFactory(), UserFactory()
        conversation_service.get_or_create_interaction(interaction, actor, users=[invited_first])

        conversation, created = conversation_service.get_or_create_interaction(
            interaction=interaction,
            actor=actor,
            users=[invited_second],
        )

        self.assertFalse(created)
        self.assertEqual(
            set(conversation.participants.values_list("user_id", flat=True)),
            {actor.pk, invited_first.pk},
        )

    def test_get_or_create_interaction_rejects_duplicate_participant_ids(self) -> None:
        """Повторяющиеся ID участников отклоняются до создания беседы."""
        interaction = InteractionFactory()
        actor, invited = UserFactory(), UserFactory()

        with self.assertRaises(ValueError):
            conversation_service.get_or_create_interaction(interaction, actor, users=[invited, invited])

    def test_get_or_create_interaction_rejects_inactive_participant(self) -> None:
        """Неактивный пользователь не может быть добавлен в чат Взаимодействия."""
        interaction = InteractionFactory()
        actor = UserFactory()
        inactive = UserFactory(is_active=False)

        with self.assertRaises(ValueError):
            conversation_service.get_or_create_interaction(interaction, actor, users=[inactive])

    def test_add_participants_adds_only_missing_users(self) -> None:
        """add_participants добавляет только пользователей, которых ещё нет в чате."""
        interaction = InteractionFactory()
        actor, existing, new_user = UserFactory(), UserFactory(), UserFactory()
        conversation, _ = conversation_service.get_or_create_interaction(interaction, actor, users=[existing])

        added = conversation_service.add_participants(conversation, [existing, new_user])

        self.assertEqual([user.pk for user in added], [new_user.pk])
        self.assertEqual(
            set(conversation.participants.values_list("user_id", flat=True)),
            {actor.pk, existing.pk, new_user.pk},
        )

    def test_can_add_participants_true_for_creator(self) -> None:
        """Создатель чата всегда может добавлять участников."""
        interaction = InteractionFactory()
        actor = UserFactory()
        conversation, _ = conversation_service.get_or_create_interaction(interaction, actor)

        self.assertTrue(conversation_service.can_add_participants(conversation, actor))

    def test_can_add_participants_true_for_head_and_admin(self) -> None:
        """Руководитель и администратор платформы могут добавлять участников, даже не будучи создателем."""
        interaction = InteractionFactory()
        actor = UserFactory()
        conversation, _ = conversation_service.get_or_create_interaction(interaction, actor)

        head, admin = UserFactory(), UserFactory()
        UserRole.objects.create(user=head, role=SystemRole.HEAD)
        UserRole.objects.create(user=admin, role=SystemRole.PLATFORM_ADMIN)

        self.assertTrue(conversation_service.can_add_participants(conversation, head))
        self.assertTrue(conversation_service.can_add_participants(conversation, admin))

    def test_can_add_participants_false_for_unrelated_kam(self) -> None:
        """КАМ, не создававший чат, не может менять его состав."""
        interaction = InteractionFactory()
        actor = UserFactory()
        conversation, _ = conversation_service.get_or_create_interaction(interaction, actor)

        other_kam = UserFactory()
        UserRole.objects.create(user=other_kam, role=SystemRole.KAM)

        self.assertFalse(conversation_service.can_add_participants(conversation, other_kam))
