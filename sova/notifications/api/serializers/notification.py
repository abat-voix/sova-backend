from rest_framework import serializers

from sova.notifications.models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    """Уведомление в системе — только чтение."""

    kind_label = serializers.CharField(
        source="get_kind_display",
        read_only=True,
        label="Название группы",
    )

    class Meta:
        model = Notification
        fields = (
            "id",
            "title",
            "text",
            "is_read",
            "kind",
            "kind_label",
            "link",
            "created_at",
        )
        read_only_fields = fields


class NotificationKindSerializer(serializers.Serializer):
    """Группа уведомлений со счётчиками текущего пользователя."""

    value = serializers.CharField(label="Код группы")
    label = serializers.CharField(label="Название группы")
    icon = serializers.CharField(label="Иконка", help_text="Имя иконки lucide")
    count = serializers.IntegerField(label="Уведомлений")
    unread_count = serializers.IntegerField(label="Непрочитанных")


class UnreadCountSerializer(serializers.Serializer):
    """Число непрочитанных уведомлений."""

    count = serializers.IntegerField(label="Непрочитанных")


class ReadAllResultSerializer(serializers.Serializer):
    """Результат «прочитать все»."""

    updated = serializers.IntegerField(label="Отмечено прочитанными")
