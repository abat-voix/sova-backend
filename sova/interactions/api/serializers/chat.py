from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers


class ParticipantIdsSerializer(serializers.Serializer):
    """Список ID активных пользователей для управления составом чата Взаимодействия."""

    participant_ids = serializers.ListField(
        child=serializers.PrimaryKeyRelatedField(queryset=get_user_model().objects.filter(is_active=True)),
        allow_empty=True,
        default=list,
        max_length=50,
    )

    def validate_participant_ids(self, users: list) -> list:
        """ID участников не должны повторяться."""
        ids = [user.pk for user in users]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError(_("Идентификаторы участников не должны повторяться."))
        return users


class CreateInteractionChatSerializer(ParticipantIdsSerializer):
    """Создание (или получение существующего) чата Взаимодействия с составом участников."""


class AddChatParticipantsSerializer(ParticipantIdsSerializer):
    """Добавление участников в существующий чат Взаимодействия."""
