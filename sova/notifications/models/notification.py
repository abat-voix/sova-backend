from django.conf import settings
from django.db import models

from sova.core.models import TimeStampedModel
from sova.notifications.enum import NotificationKind


class Notification(TimeStampedModel):
    """
    Уведомление в системе («колокольчик»): что показать пользователю в интерфейсе.

    Создаёт канал NotificationChannel.SYSTEM; удаляет задача cleanup_notifications по сроку хранения.
    """

    title = models.CharField(
        max_length=255,
        verbose_name="Заголовок",
    )
    text = models.TextField(
        blank=True,
        verbose_name="Текст",
    )
    kind = models.CharField(
        max_length=20,
        choices=NotificationKind.choices,
        default=NotificationKind.SYSTEM,
        verbose_name="Группа",
    )
    link = models.CharField(
        max_length=500,
        blank=True,
        verbose_name="Ссылка",
        help_text="Адрес объекта в интерфейсе; пусто — уведомление без перехода.",
    )
    is_read = models.BooleanField(
        default=False,
        verbose_name="Прочитано",
    )

    recipient = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name="Получатель",
    )

    class Meta:
        verbose_name = "Уведомление"
        verbose_name_plural = "Уведомления"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "is_read"], name="notification_recipient_read"),
        ]

    def __str__(self):
        return self.title
