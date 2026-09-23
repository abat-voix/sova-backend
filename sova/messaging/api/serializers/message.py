from rest_framework import serializers

from sova.core.api.serializers import UserShortSerializer
from sova.messaging.models import Message


class MessageSerializer(serializers.ModelSerializer):
    """Сообщение — представление для чтения."""

    sender = UserShortSerializer(read_only=True)

    class Meta:
        model = Message
        fields = ("id", "conversation", "sender", "text", "link", "created_at")


class SendMessageSerializer(serializers.Serializer):
    """Отправка сообщения в беседу — валидация входных данных."""

    text = serializers.CharField()
    link = serializers.CharField(required=False, allow_blank=True, default="")
