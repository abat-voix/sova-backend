from django.conf import settings
from django.db import models

from sova.core.files import uuid_upload_to
from sova.core.models import TimeStampedModel


class MessageAttachment(TimeStampedModel):
    """Файл, ожидающий отправки или уже приложенный к сообщению."""

    message = models.ForeignKey(
        "messaging.Message",
        related_name="attachments",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        verbose_name="Сообщение",
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="message_attachments",
        on_delete=models.SET_NULL,
        null=True,
        verbose_name="Загрузил",
    )
    file = models.FileField(upload_to=uuid_upload_to("message_attachments"), max_length=500, verbose_name="Файл")
    original_name = models.CharField(max_length=255, verbose_name="Исходное имя файла")
    size = models.PositiveBigIntegerField(verbose_name="Размер файла, байт")
    content_type = models.CharField(max_length=255, verbose_name="MIME-тип")

    class Meta:
        verbose_name = "Вложение сообщения"
        verbose_name_plural = "Вложения сообщений"
        indexes = [
            models.Index(
                fields=["uploaded_by", "message", "created_at"],
                name="msg_attach_owner_pending_idx",
            ),
        ]

    def __str__(self) -> str:
        return self.original_name
