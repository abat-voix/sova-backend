from rest_framework import serializers

from sova.core.api.serializers import UserShortSerializer
from sova.messaging.models import Message
from sova.messaging.presentation import message_representation


class MessageSerializer(serializers.ModelSerializer):
    """Сообщение — представление для чтения."""

    sender = UserShortSerializer(read_only=True)

    class Meta:
        model = Message
        fields = ("id", "conversation", "sender", "text", "link", "attachments", "created_at")

    def to_representation(self, instance: Message) -> dict:
        return message_representation(instance)


class SendMessageSerializer(serializers.Serializer):
    """Отправка сообщения в беседу — валидация входных данных."""

    text = serializers.CharField(required=False, allow_blank=True, default="")
    link = serializers.CharField(required=False, allow_blank=True, default="")
    attachment_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, default=list, max_length=10
    )

    def validate(self, attrs):
        if not attrs["text"].strip() and not attrs["attachment_ids"]:
            raise serializers.ValidationError("Сообщение должно содержать текст или вложение.", code="empty_message")
        return attrs
