from rest_framework import serializers


class TelegramLinkStatusSerializer(serializers.Serializer):
    """Статус привязки Telegram: подключён ли, и ссылка для подключения, если нет."""

    is_connected = serializers.BooleanField(read_only=True)
    deep_link = serializers.CharField(read_only=True, allow_null=True)
    expires_at = serializers.DateTimeField(read_only=True, allow_null=True)
