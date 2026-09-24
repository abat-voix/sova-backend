from rest_framework import serializers


class IntegrationMessageResponseSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    status = serializers.CharField()
    duplicate = serializers.BooleanField()


class IntegrationPayloadSerializer(serializers.Serializer):
    """Documentation-only serializer: integration payload is intentionally open-ended."""

    payload = serializers.JSONField()
