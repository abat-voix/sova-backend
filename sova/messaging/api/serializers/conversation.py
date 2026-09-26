from django.contrib.auth import get_user_model
from rest_framework import serializers

from sova.core.api.serializers import UserShortSerializer
from sova.messaging.api.serializers.message import MessageSerializer
from sova.messaging.models import Conversation
from sova.messaging.services import message_service


class ConversationSerializer(serializers.ModelSerializer):
    """
    Беседа — представление для чтения.

    other_participant, last_message и unread_count считаются относительно
    пользователя из request.context — сериализатор требует context={"request": ...}.
    """

    other_participant = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = (
            "id",
            "kind",
            "other_participant",
            "last_message",
            "unread_count",
            "last_message_at",
        )

    def get_other_participant(self, instance: Conversation) -> dict | None:
        """Собеседник в личной беседе; для системной беседы отсутствует."""
        user = self.context["request"].user
        participant = next(
            (p for p in instance.participants.all() if p.user_id != user.pk),
            None,
        )
        return UserShortSerializer(participant.user).data if participant else None

    def get_last_message(self, instance: Conversation) -> dict | None:
        """Последнее сообщение беседы для превью в списке."""
        message = instance.messages.select_related("sender").prefetch_related("attachments").order_by("-created_at").first()
        return MessageSerializer(message).data if message else None

    def get_unread_count(self, instance: Conversation) -> int:
        """Число непрочитанных сообщений текущего пользователя в этой беседе."""
        user = self.context["request"].user
        return message_service.conversation_unread_count(instance, user)


class CreateDirectConversationSerializer(serializers.Serializer):
    """Создание (или получение существующей) личной беседы с другим пользователем."""

    user = serializers.PrimaryKeyRelatedField(queryset=get_user_model().objects.all())


class ConversationRecipientSerializer(serializers.ModelSerializer):
    """Минимальные данные активного пользователя для выбора собеседника."""

    full_name = serializers.SerializerMethodField()

    class Meta:
        model = get_user_model()
        fields = ("id", "full_name")

    def get_full_name(self, instance) -> str:
        """ФИО пользователя или логин, если ФИО не заполнено."""
        return instance.get_full_name() or instance.get_username()
