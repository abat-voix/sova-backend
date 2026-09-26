from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from sova.core.files import file_response
from sova.messaging.api import serializers
from sova.messaging.models import MessageAttachment
from sova.messaging.services.message_attachment import AttachmentNotFoundError, message_attachment_service


class MessageAttachmentViewSet(mixins.CreateModelMixin, mixins.DestroyModelMixin, GenericViewSet):
    """Подготовка файлов перед JSON-отправкой сообщения и защищённое скачивание."""

    serializer_class = serializers.MessageAttachmentUploadSerializer
    queryset = MessageAttachment.objects.all()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        attachment = message_attachment_service.stage(request.user, serializer.validated_data["file"])
        return Response(
            serializers.StagedMessageAttachmentSerializer(attachment).data,
            status=status.HTTP_201_CREATED,
            headers=self.get_success_headers(serializer.data),
        )

    def destroy(self, request, *args, **kwargs):
        attachment = self.get_object()
        try:
            message_attachment_service.delete_staged(request.user, attachment)
        except AttachmentNotFoundError as exc:
            raise NotFound(detail="Вложение не найдено.", code="attachment_not_found") from exc
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        responses={
            (200, "application/octet-stream"): OpenApiResponse(OpenApiTypes.BINARY),
            404: OpenApiResponse(description="Вложение не найдено или недоступно"),
            410: OpenApiResponse(description="Файл больше недоступен в хранилище"),
        },
    )
    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        attachment = self.get_object()
        is_staged_owner = attachment.message_id is None and attachment.uploaded_by_id == request.user.pk
        is_participant = (
            attachment.message_id is not None
            and attachment.message.conversation.participants.filter(user=request.user).exists()
        )
        if not (is_staged_owner or is_participant):
            raise NotFound(detail="Вложение не найдено.", code="attachment_not_found")
        return file_response(attachment.file, attachment.original_name, content_type=attachment.content_type)

    def get_queryset(self):
        # get_object() не раскрывает ID: дополнительная проверка прав download остаётся
        # нужна для staging-файлов и для удаления.
        return super().get_queryset().select_related("message__conversation")
