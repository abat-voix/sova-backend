from django.conf import settings
from django.db import models

from sova.core.files import uuid_upload_to
from sova.core.models import UUIDModel


class ActionAttachment(UUIDModel):
    """Файл, приложенный к экземпляру действия. Запись журнала — не редактируется."""

    file = models.FileField(
        upload_to=uuid_upload_to("action_attachments"),
        max_length=500,
        verbose_name="Файл",
    )
    # Имя, под которым файл загрузил пользователь: ключ файла (`file.name`) — случайный UUID,
    # исходное имя нужно отдельно, чтобы показать его в интерфейсе и вернуть при скачивании.
    original_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Исходное имя файла",
    )
    size = models.PositiveBigIntegerField(
        null=True,
        blank=True,
        verbose_name="Размер файла, байт",
    )
    content_type = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="MIME-тип",
    )
    uploaded_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Загружен",
    )

    action_instance = models.ForeignKey(
        to="processes.ActionInstance",
        on_delete=models.CASCADE,
        related_name="action_attachments",
        verbose_name="Экземпляр действия",
    )
    uploaded_by = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="action_attachments",
        null=True,
        blank=True,
        verbose_name="Кто загрузил",
    )

    class Meta:
        verbose_name = "Вложение действия"
        verbose_name_plural = "Вложения действий"
        ordering = ["-uploaded_at"]

    def __str__(self):
        return self.file.name
