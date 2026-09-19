from django.conf import settings
from django.db import models

from sova.crm.models.base import UUIDModel


class ActionAttachment(UUIDModel):
    """Файл, приложенный к экземпляру действия. Запись журнала — не редактируется."""

    file = models.FileField(
        upload_to="action_attachments/%Y/%m/",
        verbose_name="Файл",
    )
    uploaded_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Загружен",
    )

    action_instance = models.ForeignKey(
        to="crm.ActionInstance",
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
