from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction
from django.utils import timezone

from sova.messaging.enum import ConversationKind
from sova.messaging.exceptions import NotConversationParticipantError, SystemConversationIsReadOnlyError
from sova.messaging.models import Conversation, ConversationParticipant, Message


class MessageService:
    """Отправка сообщений и учёт прочтения в личных беседах."""

    @transaction.atomic
    def send(self, conversation: Conversation, sender: AbstractBaseUser, text: str, link: str = "") -> Message:
        """
        Отправляет сообщение от участника беседы.

        Отправитель считается прочитавшим беседу по момент своего сообщения —
        last_read_at сдвигается вместе с отправкой, отдельного вызова mark_read
        для собственных сообщений не требуется.
        """
        if conversation.kind == ConversationKind.SYSTEM:
            raise SystemConversationIsReadOnlyError

        updated_participants = ConversationParticipant.objects.filter(
            conversation=conversation,
            user=sender,
        ).update(last_read_at=timezone.now())
        if not updated_participants:
            raise NotConversationParticipantError

        message = Message.objects.create(conversation=conversation, sender=sender, text=text, link=link)
        conversation.last_message_at = message.created_at
        conversation.save(update_fields=["last_message_at"])
        return message

    def mark_read(self, conversation: Conversation, user: AbstractBaseUser) -> None:
        """Отмечает беседу прочитанной пользователем по текущий момент."""
        updated = ConversationParticipant.objects.filter(conversation=conversation, user=user).update(
            last_read_at=timezone.now(),
        )
        if not updated:
            raise NotConversationParticipantError

    def unread_count(self, user: AbstractBaseUser) -> int:
        """Суммарное число непрочитанных сообщений пользователя по всем беседам."""
        total = 0
        participations = ConversationParticipant.objects.filter(user=user).values(
            "conversation_id",
            "last_read_at",
        )
        for participation in participations:
            total += self._unread_count(
                conversation_id=participation["conversation_id"],
                last_read_at=participation["last_read_at"],
                user=user,
            )
        return total

    def conversation_unread_count(self, conversation: Conversation, user: AbstractBaseUser) -> int:
        """Число непрочитанных сообщений пользователя в одной беседе."""
        participant = ConversationParticipant.objects.filter(conversation=conversation, user=user).first()
        if participant is None:
            return 0
        return self._unread_count(conversation_id=conversation.pk, last_read_at=participant.last_read_at, user=user)

    def _unread_count(self, conversation_id, last_read_at, user: AbstractBaseUser) -> int:
        messages = Message.objects.filter(conversation_id=conversation_id).exclude(sender=user)
        if last_read_at is not None:
            messages = messages.filter(created_at__gt=last_read_at)
        return messages.count()


message_service = MessageService()
