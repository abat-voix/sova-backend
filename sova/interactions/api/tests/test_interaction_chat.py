from unittest.mock import patch

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import SystemRole, UserRole
from sova.core.tests.factories import UserFactory
from sova.interactions.tests.factories import InteractionFactory, ResponsibleFactory
from sova.messaging.models import Conversation
from sova.messaging.services.conversation import conversation_service
from sova.messaging.services.message import message_service


class InteractionChatApiTestCase(APITestCase):
    """Тесты /api/interactions/interactions/{id}/chat/ и .../chat/participants/."""

    def setUp(self) -> None:
        self.kam = UserFactory()
        UserRole.objects.create(user=self.kam, role=SystemRole.KAM)
        self.interaction = InteractionFactory()
        ResponsibleFactory(interaction=self.interaction, manager=self.kam)
        self.client.force_authenticate(user=self.kam)

    def chat_url(self, interaction=None) -> str:
        return reverse("interactions:interaction-chat", args=[(interaction or self.interaction).pk])

    def participants_url(self, interaction=None) -> str:
        return reverse("interactions:interaction-chat-participants", args=[(interaction or self.interaction).pk])

    def test_get_returns_404_when_chat_not_created(self) -> None:
        """GET до создания чата — 404."""
        response = self.client.get(self.chat_url())

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_post_creates_chat_with_actor_as_participant(self) -> None:
        """POST создаёт чат и делает автора его участником; 201 при создании."""
        response = self.client.post(self.chat_url(), data={"participant_ids": []}, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["interaction_id"], self.interaction.pk)
        self.assertEqual(
            {p["id"] for p in response.data["participants"]},
            {self.kam.pk},
        )

    def test_post_invites_participant_ids_on_creation(self) -> None:
        """POST с participant_ids добавляет их в состав вместе с автором."""
        head = UserFactory()
        UserRole.objects.create(user=head, role=SystemRole.HEAD)

        response = self.client.post(self.chat_url(), data={"participant_ids": [head.pk]}, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            {p["id"] for p in response.data["participants"]},
            {self.kam.pk, head.pk},
        )

    def test_post_is_idempotent_and_ignores_repeat_participant_ids(self) -> None:
        """Повторный POST возвращает тот же чат (200) и не добавляет новых участников."""
        first = self.client.post(self.chat_url(), data={"participant_ids": []}, format="json")
        other = UserFactory()

        second = self.client.post(self.chat_url(), data={"participant_ids": [other.pk]}, format="json")

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(
            {p["id"] for p in second.data["participants"]},
            {self.kam.pk},
        )

    def test_post_rejects_invisible_interaction(self) -> None:
        """Взаимодействие, недоступное пользователю по роли, отдаёт 404 вместо создания чата."""
        other_interaction = InteractionFactory()
        ResponsibleFactory(interaction=other_interaction, manager=UserFactory())

        response = self.client.post(self.chat_url(other_interaction), data={"participant_ids": []}, format="json")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_post_rejects_duplicate_participant_ids(self) -> None:
        """Повторяющиеся ID в теле запроса отклоняются как ошибка валидации."""
        other = UserFactory()

        response = self.client.post(
            self.chat_url(),
            data={"participant_ids": [other.pk, other.pk]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_get_hides_chat_from_non_participant(self) -> None:
        """GET возвращает 404, если чат существует, но пользователь не приглашён."""
        conversation_service.get_or_create_interaction(self.interaction, self.kam)
        head = UserFactory()
        UserRole.objects.create(user=head, role=SystemRole.HEAD)
        self.client.force_authenticate(user=head)

        response = self.client.get(self.chat_url())

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_post_by_non_participant_does_not_leak_history(self) -> None:
        """POST не приглашённого в уже созданный чат пользователя не отдаёт его содержимое."""
        conversation, _ = conversation_service.get_or_create_interaction(self.interaction, self.kam)
        message_service.send(conversation=conversation, sender=self.kam, text="Секрет")
        head = UserFactory()
        UserRole.objects.create(user=head, role=SystemRole.HEAD)
        self.client.force_authenticate(user=head)

        response = self.client.post(self.chat_url(), data={"participant_ids": []}, format="json")

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "chat_exists_not_participant")

    def test_participants_action_adds_by_creator(self) -> None:
        """Создатель чата может пригласить нового участника."""
        conversation_service.get_or_create_interaction(self.interaction, self.kam)
        head = UserFactory()
        UserRole.objects.create(user=head, role=SystemRole.HEAD)

        response = self.client.post(self.participants_url(), data={"participant_ids": [head.pk]}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {p["id"] for p in response.data["participants"]},
            {self.kam.pk, head.pk},
        )

    def test_participants_action_allowed_for_head_who_is_not_creator(self) -> None:
        """Руководитель может добавлять участников, даже не создав чат сам."""
        conversation_service.get_or_create_interaction(self.interaction, self.kam)
        head = UserFactory()
        UserRole.objects.create(user=head, role=SystemRole.HEAD)
        self.client.force_authenticate(user=head)
        new_user = UserFactory()

        response = self.client.post(self.participants_url(), data={"participant_ids": [new_user.pk]}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(new_user.pk, {p["id"] for p in response.data["participants"]})

    def test_participants_action_forbidden_for_unrelated_kam(self) -> None:
        """КАМ, не создававший чат и не руководитель, не может менять состав."""
        conversation_service.get_or_create_interaction(self.interaction, self.kam)
        other_kam = UserFactory()
        UserRole.objects.create(user=other_kam, role=SystemRole.KAM)
        ResponsibleFactory(interaction=self.interaction, manager=other_kam)
        self.client.force_authenticate(user=other_kam)

        response = self.client.post(
            self.participants_url(),
            data={"participant_ids": [UserFactory().pk]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_participants_action_is_idempotent_for_existing_participant(self) -> None:
        """Повторное приглашение уже состоящего в чате пользователя не создаёт дубль."""
        conversation, _ = conversation_service.get_or_create_interaction(self.interaction, self.kam)
        head = UserFactory()
        UserRole.objects.create(user=head, role=SystemRole.HEAD)
        conversation_service.add_participants(conversation, [head])

        response = self.client.post(self.participants_url(), data={"participant_ids": [head.pk]}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            Conversation.objects.get(pk=conversation.pk).participants.filter(user=head).count(),
            1,
        )

    def test_invited_participant_sees_full_history(self) -> None:
        """Приглашённый получает доступ ко всей истории чата, включая сообщения до приглашения."""
        conversation, _ = conversation_service.get_or_create_interaction(self.interaction, self.kam)
        message_service.send(conversation=conversation, sender=self.kam, text="До приглашения")
        head = UserFactory()
        UserRole.objects.create(user=head, role=SystemRole.HEAD)
        conversation_service.add_participants(conversation, [head])
        self.client.force_authenticate(user=head)

        response = self.client.get(
            reverse("messaging:conversation-messages", args=[conversation.pk]),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([m["text"] for m in response.data["results"]], ["До приглашения"])

    def test_new_participant_receives_realtime_event_only_after_commit(self) -> None:
        """Новый участник получает messaging.conversation_created только после коммита транзакции."""
        conversation, _ = conversation_service.get_or_create_interaction(self.interaction, self.kam)
        head = UserFactory()
        UserRole.objects.create(user=head, role=SystemRole.HEAD)

        with patch("sova.messaging.realtime.async_to_sync") as async_to_sync_mock:
            sender = async_to_sync_mock.return_value
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(self.participants_url(), data={"participant_ids": [head.pk]}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        groups = {call.args[0] for call in sender.call_args_list}
        # Новому участнику — conversation_created, существующему (КАМу) — participants_added.
        self.assertEqual(groups, {f"user.{head.pk}", f"user.{self.kam.pk}"})
