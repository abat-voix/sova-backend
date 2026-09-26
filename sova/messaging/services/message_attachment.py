from collections.abc import Iterable

from django.contrib.auth.models import AbstractBaseUser
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from sova.core.files import guess_content_type
from sova.messaging.api.serializers.attachment import validate_message_attachment_file
from sova.messaging.models import Message, MessageAttachment


class AttachmentNotFoundError(Exception):
    """Запрошенное вложение отсутствует, чужое или уже использовано."""


class DuplicateAttachmentError(Exception):
    """Один идентификатор вложения передан более одного раза."""


class MessageAttachmentService:
    def stage(self, user: AbstractBaseUser, uploaded_file: UploadedFile) -> MessageAttachment:
        """Проверяет и сохраняет файл в storage как незавершённую загрузку."""
        validate_message_attachment_file(uploaded_file)
        return MessageAttachment.objects.create(
            uploaded_by=user,
            file=uploaded_file,
            original_name=uploaded_file.name,
            size=uploaded_file.size,
            content_type=guess_content_type(uploaded_file.name),
        )

    @transaction.atomic
    def claim(
        self,
        user: AbstractBaseUser,
        message: Message,
        attachment_ids: Iterable[object],
    ) -> list[MessageAttachment]:
        """Однократно привязывает подготовленные пользователем файлы к сообщению."""
        ids = list(attachment_ids)
        if len(ids) != len(set(ids)):
            raise DuplicateAttachmentError
        if not ids:
            return []

        attachments = list(
            MessageAttachment.objects.select_for_update().filter(id__in=ids).order_by("created_at")
        )
        if (
            len(attachments) != len(ids)
            or any(attachment.uploaded_by_id != user.pk or attachment.message_id for attachment in attachments)
        ):
            # Не различаем отсутствующие, чужие и уже использованные ID.
            raise AttachmentNotFoundError
        MessageAttachment.objects.filter(id__in=ids, message__isnull=True).update(message=message)
        for attachment in attachments:
            attachment.message = message
        return attachments

    @transaction.atomic
    def delete_staged(self, user: AbstractBaseUser, attachment: MessageAttachment) -> None:
        attachment = MessageAttachment.objects.select_for_update().filter(pk=attachment.pk).first()
        if attachment is None or attachment.uploaded_by_id != user.pk or attachment.message_id:
            raise AttachmentNotFoundError
        storage, name = attachment.file.storage, attachment.file.name
        attachment.delete()
        transaction.on_commit(lambda: storage.delete(name))

    @transaction.atomic
    def cleanup_staged(self, before) -> int:
        attachments = list(
            MessageAttachment.objects.select_for_update().filter(message__isnull=True, created_at__lt=before)
        )
        files = [(attachment.file.storage, attachment.file.name) for attachment in attachments]
        MessageAttachment.objects.filter(pk__in=[attachment.pk for attachment in attachments]).delete()
        for storage, name in files:
            transaction.on_commit(lambda storage=storage, name=name: storage.delete(name))
        return len(attachments)


message_attachment_service = MessageAttachmentService()
