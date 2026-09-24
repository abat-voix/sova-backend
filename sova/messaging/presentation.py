from rest_framework.fields import DateTimeField

from sova.core.api.serializers import UserShortSerializer
from sova.messaging.models import Message


def message_representation(message: Message) -> dict:
    """Canonical JSON representation shared by REST and realtime."""
    return {
        "id": str(message.pk),
        "conversation": str(message.conversation_id),
        "sender": UserShortSerializer(message.sender).data if message.sender_id else None,
        "text": message.text,
        "link": message.link,
        "created_at": DateTimeField().to_representation(message.created_at),
    }
