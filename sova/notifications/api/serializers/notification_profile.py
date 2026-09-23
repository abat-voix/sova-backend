from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.core.api.serializers import UserShortSerializer
from sova.notifications.models import NotificationProfile


class NotificationProfileSerializer(serializers.ModelSerializer):
    """Профиль уведомлений — представление для чтения (list/retrieve)."""

    user = UserShortSerializer(
        read_only=True,
        label=_("Пользователь"),
        help_text=_("Показывается развёрнуто, для записи см. write-сериализатор"),
    )

    class Meta:
        model = NotificationProfile
        fields = (
            "id",
            "user",
            "email",
            "telegram_chat_id",
            "max_chat_id",
        )


class WriteNotificationProfileSerializer(serializers.ModelSerializer):
    """Профиль уведомлений — валидация входных данных (create/update)."""

    class Meta:
        model = NotificationProfile
        fields = (
            "id",
            "user",
            "email",
            "telegram_chat_id",
            "max_chat_id",
        )
