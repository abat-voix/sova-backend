from django.conf import settings
from django.db import models

from sova.core.models import UUIDModel
from sova.notifications.enum import DEADLINE_NOTIFY_TYPES, NotificationChannel, NotifyEvent, NotifyType


class DeadlineDelivery(UUIDModel):
    """
    Журнал: получатель успешно получил уведомление о пункте с этим сроком по этому каналу.

    Ключ включает deadline: при сбросе действия на месте или откате этапа срок пересчитывается,
    и новая просрочка уведомляется заново без правок движка. Ключ включает получателя: недоставленное
    повторяется только тому, кому не дошло. Ключ включает канал: недоставленное повторяется только по упавшему
    каналу, без дублей в остальных.
    """

    notify_type = models.CharField(
        max_length=20,
        choices=[choice for choice in NotifyType.choices if choice[0] in DEADLINE_NOTIFY_TYPES],
        verbose_name="Тип уведомления",
    )
    event = models.CharField(
        max_length=20,
        choices=NotifyEvent.choices,
        verbose_name="Событие",
    )
    channel = models.CharField(
        max_length=20,
        choices=NotificationChannel.choices,
        verbose_name="Канал",
    )
    object_id = models.UUIDField(
        verbose_name="ID объекта",
        help_text="ActionInstance, StageInstance или WorkflowInstance — по виду контроля.",
    )
    deadline = models.DateTimeField(
        verbose_name="Срок",
    )
    last_sent_at = models.DateTimeField(
        verbose_name="Последняя отправка",
    )
    send_count = models.PositiveIntegerField(
        default=1,
        verbose_name="Отправлено раз",
    )

    recipient = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="deadline_deliveries",
        verbose_name="Получатель",
    )

    class Meta:
        verbose_name = "Уведомление о сроке"
        verbose_name_plural = "Журнал уведомлений о сроках"
        ordering = ["-last_sent_at"]
        indexes = [
            models.Index(fields=["object_id"], name="deadline_delivery_object"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["notify_type", "event", "object_id", "deadline", "recipient", "channel"],
                name="unique_deadline_delivery",
            ),
        ]

    def __str__(self):
        parts = (self.get_notify_type_display(), self.get_event_display(), str(self.recipient), self.get_channel_display())
        return " — ".join(parts)
