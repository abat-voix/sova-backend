from django.contrib.auth import get_user_model
from rest_framework import serializers

from sova.core.api.serializers import UserShortSerializer
from sova.messaging.api.serializers.message import MessageSerializer
from sova.messaging.enum import ConversationKind
from sova.messaging.models import Conversation

# Импорт сервисов внутри методов, а не на уровне модуля: message_service тянет
# message_attachment -> serializers.attachment -> serializers/__init__, который
# импортирует этот же модуль, — на уровне модуля это цикл импорта.


class ConversationSerializer(serializers.ModelSerializer):
    """
    Беседа — представление для чтения.

    other_participant, last_message, unread_count и can_manage_participants
    считаются относительно пользователя из request.context — сериализатор
    требует context={"request": ...}.
    """

    other_participant = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    interaction_id = serializers.PrimaryKeyRelatedField(source="interaction", read_only=True)
    title = serializers.SerializerMethodField()
    participants = serializers.SerializerMethodField()
    can_manage_participants = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = (
            "id",
            "kind",
            "other_participant",
            "interaction_id",
            "title",
            "participants",
            "can_manage_participants",
            "last_message",
            "unread_count",
            "last_message_at",
        )

    def get_other_participant(self, instance: Conversation) -> dict | None:
        """Собеседник в личной беседе; для остальных типов беседы отсутствует."""
        if instance.kind != ConversationKind.DIRECT:
            return None
        user = self.context["request"].user
        participant = next(
            (p for p in instance.participants.all() if p.user_id != user.pk),
            None,
        )
        return UserShortSerializer(participant.user).data if participant else None

    def get_title(self, instance: Conversation) -> str | None:
        """Название чата Взаимодействия — по его вузу или B2C-клиенту; для остальных типов отсутствует."""
        if instance.kind != ConversationKind.INTERACTION or instance.interaction_id is None:
            return None
        interaction = instance.interaction
        return str(interaction.university or interaction.b2c_client)

    def get_participants(self, instance: Conversation) -> list[dict] | None:
        """Состав чата Взаимодействия; для остальных типов беседы отсутствует."""
        if instance.kind != ConversationKind.INTERACTION:
            return None
        return UserShortSerializer((p.user for p in instance.participants.all()), many=True).data

    def get_can_manage_participants(self, instance: Conversation) -> bool | None:
        """Право текущего пользователя добавлять участников чата Взаимодействия."""
        if instance.kind != ConversationKind.INTERACTION:
            return None
        from sova.messaging.services.conversation import conversation_service

        return conversation_service.can_add_participants(instance, self.context["request"].user)

    def get_last_message(self, instance: Conversation) -> dict | None:
        """Последнее сообщение беседы для превью в списке."""
        message = instance.messages.select_related("sender").prefetch_related("attachments").order_by("-created_at").first()
        return MessageSerializer(message).data if message else None

    def get_unread_count(self, instance: Conversation) -> int:
        """Число непрочитанных сообщений текущего пользователя в этой беседе."""
        from sova.messaging.services.message import message_service

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
