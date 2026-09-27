from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import SystemRole, UserRole
from sova.core.tests.factories import UserFactory
from sova.messaging.services import conversation_service, message_service, send_system_message


class ConversationApiTestCase(APITestCase):
    """Тесты /api/messaging/conversations/."""

    def setUp(self) -> None:
        self.user = UserFactory()
        UserRole.objects.create(user=self.user, role=SystemRole.KAM)
        self.client.force_authenticate(user=self.user)

    def test_list_shows_only_own_conversations(self) -> None:
        """Список бесед не включает чужие переписки."""
        other_a, other_b = UserFactory(), UserFactory()
        own = conversation_service.get_or_create_direct(self.user, other_a)
        conversation_service.get_or_create_direct(other_a, other_b)

        response = self.client.get(reverse("messaging:conversation-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {item["id"] for item in response.data}
        self.assertEqual(ids, {str(own.pk)})

    def test_direct_action_creates_conversation_and_is_idempotent(self) -> None:
        """POST /conversations/direct/ создаёт беседу и возвращает ту же при повторе."""
        other_user = UserFactory()

        first = self.client.post(reverse("messaging:conversation-direct"), data={"user": str(other_user.pk)})
        second = self.client.post(reverse("messaging:conversation-direct"), data={"user": str(other_user.pk)})

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(first.data["other_participant"]["id"], other_user.pk)

    def test_direct_action_rejects_self(self) -> None:
        """Нельзя открыть личную беседу с самим собой."""
        response = self.client.post(reverse("messaging:conversation-direct"), data={"user": str(self.user.pk)})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_get_messages_returns_conversation_history(self) -> None:
        """GET /conversations/{id}/messages/ возвращает историю переписки."""
        other_user = UserFactory()
        conversation = conversation_service.get_or_create_direct(self.user, other_user)
        message_service.send(conversation=conversation, sender=self.user, text="Привет")

        response = self.client.get(
            reverse("messaging:conversation-messages", args=[conversation.pk]),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["text"], "Привет")

    def test_post_messages_sends_message(self) -> None:
        """POST /conversations/{id}/messages/ отправляет сообщение от текущего пользователя."""
        other_user = UserFactory()
        conversation = conversation_service.get_or_create_direct(self.user, other_user)

        response = self.client.post(
            reverse("messaging:conversation-messages", args=[conversation.pk]),
            data={"text": "Привет!"},
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["text"], "Привет!")
        self.assertEqual(response.data["sender"]["id"], self.user.pk)

    def test_post_messages_to_system_conversation_is_rejected(self) -> None:
        """Нельзя отправить сообщение в свою системную беседу через API."""
        conversation = conversation_service.get_or_create_system(self.user)

        response = self.client.post(
            reverse("messaging:conversation-messages", args=[conversation.pk]),
            data={"text": "Привет!"},
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "system_conversation_read_only")

    def test_cannot_access_foreign_conversation(self) -> None:
        """Чужая беседа возвращает 404 — как retrieve, так и вложенные действия."""
        other_a, other_b = UserFactory(), UserFactory()
        foreign = conversation_service.get_or_create_direct(other_a, other_b)

        retrieve = self.client.get(reverse("messaging:conversation-detail", args=[foreign.pk]))
        messages = self.client.get(reverse("messaging:conversation-messages", args=[foreign.pk]))

        self.assertEqual(retrieve.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(messages.status_code, status.HTTP_404_NOT_FOUND)

    def test_read_action_resets_unread_count(self) -> None:
        """POST /conversations/{id}/read/ обнуляет непрочитанное в этой беседе."""
        other_user = UserFactory()
        conversation = conversation_service.get_or_create_direct(self.user, other_user)
        message_service.send(conversation=conversation, sender=other_user, text="Привет")

        response = self.client.post(reverse("messaging:conversation-read", args=[conversation.pk]))

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(message_service.unread_count(self.user), 0)

    def test_unread_count_action_sums_direct_and_system_messages(self) -> None:
        """GET /conversations/unread-count/ учитывает и личные, и системные сообщения."""
        other_user = UserFactory()
        conversation = conversation_service.get_or_create_direct(self.user, other_user)
        message_service.send(conversation=conversation, sender=other_user, text="Привет")
        send_system_message([self.user], text="Системное уведомление")

        response = self.client.get(reverse("messaging:conversation-unread-count"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["unread_count"], 2)

    def test_requires_authentication(self) -> None:
        """Неаутентифицированный запрос отклоняется."""
        self.client.force_authenticate(user=None)

        response = self.client.get(reverse("messaging:conversation-list"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
