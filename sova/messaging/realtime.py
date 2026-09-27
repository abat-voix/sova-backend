import logging
from collections.abc import Iterable

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction

from sova.messaging.models import Conversation, ConversationParticipant, Message
from sova.messaging.presentation import message_representation
from sova.realtime.events import RealtimeEvent, build_event
from sova.realtime.groups import user_group_name


logger = logging.getLogger(__name__)


def _publish_after_commit(event: RealtimeEvent, recipient_ids: Iterable[object]) -> None:
    recipients = tuple(dict.fromkeys(str(user_id) for user_id in recipient_ids))
    envelope = event.as_dict()

    def send() -> None:
        try:
            channel_layer = get_channel_layer()
            if channel_layer is None:
                raise RuntimeError("Default channel layer is not configured.")
            for user_id in recipients:
                async_to_sync(channel_layer.group_send)(
                    user_group_name(user_id),
                    {"type": "realtime.event", "event": envelope},
                )
        except Exception:
            logger.exception(
                "Realtime publish failed event_id=%s event_type=%s recipients=%d",
                event.id,
                event.type,
                len(recipients),
            )

    transaction.on_commit(send)


def publish_message_created(message: Message) -> None:
    recipient_ids = list(
        ConversationParticipant.objects.filter(conversation_id=message.conversation_id)
        .order_by()
        .values_list("user_id", flat=True)
    )
    event = build_event(
        "messaging.message_created",
        {
            "conversation_id": str(message.conversation_id),
            "message": message_representation(message),
        },
    )
    _publish_after_commit(event, recipient_ids)


def publish_conversation_created(conversation: Conversation, recipient_ids: Iterable[object] | None = None) -> None:
    """Оповещает о появлении беседы. Без recipient_ids — всех текущих участников."""
    if recipient_ids is None:
        recipient_ids = list(
            ConversationParticipant.objects.filter(conversation=conversation)
            .order_by()
            .values_list("user_id", flat=True)
        )
    event = build_event(
        "messaging.conversation_created",
        {"conversation_id": str(conversation.pk)},
    )
    _publish_after_commit(event, recipient_ids)


def publish_participants_added(conversation: Conversation, new_user_ids: Iterable[object]) -> None:
    """Оповещает уже бывших участников чата о новых людях в составе."""
    new_user_ids = list(dict.fromkeys(str(user_id) for user_id in new_user_ids))
    recipient_ids = list(
        ConversationParticipant.objects.filter(conversation=conversation)
        .exclude(user_id__in=new_user_ids)
        .order_by()
        .values_list("user_id", flat=True)
    )
    event = build_event(
        "messaging.participants_added",
        {"conversation_id": str(conversation.pk), "user_ids": new_user_ids},
    )
    _publish_after_commit(event, recipient_ids)


def publish_conversation_read(conversation: Conversation, user, read_at) -> None:
    event = build_event(
        "messaging.conversation_read",
        {
            "conversation_id": str(conversation.pk),
            "read_at": read_at.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        },
    )
    _publish_after_commit(event, [user.pk])
