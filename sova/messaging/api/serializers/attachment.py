from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import FileExtensionValidator
from django.urls import reverse
from rest_framework import serializers

from sova.core.files import ALLOWED_ATTACHMENT_EXTENSIONS, validate_file_size
from sova.messaging.models import MessageAttachment


_file_validator = FileExtensionValidator(allowed_extensions=ALLOWED_ATTACHMENT_EXTENSIONS)


def validate_message_attachment_file(uploaded_file) -> None:
    """Единые с вложениями действий ограничения расширения и размера."""
    try:
        _file_validator(uploaded_file)
        validate_file_size(uploaded_file)
    except DjangoValidationError as exc:
        raise serializers.ValidationError(exc.messages, code="invalid_file") from exc


class MessageAttachmentUploadSerializer(serializers.Serializer):
    file = serializers.FileField(write_only=True)

    def validate_file(self, value):
        validate_message_attachment_file(value)
        return value


class MessageAttachmentSerializer(serializers.ModelSerializer):
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = MessageAttachment
        fields = ("id", "original_name", "size", "content_type", "download_url")

    def get_download_url(self, obj: MessageAttachment) -> str:
        return reverse("messaging:message-attachment-download", args=[obj.pk])


class StagedMessageAttachmentSerializer(serializers.ModelSerializer):
    """Ответ upload endpoint: ссылка появляется только в представлении сообщения."""

    class Meta:
        model = MessageAttachment
        fields = ("id", "original_name", "size", "content_type")
