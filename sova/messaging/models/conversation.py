from django.db import models

from sova.core.models import TimeStampedModel
from sova.messaging.enum import ConversationKind


class Conversation(TimeStampedModel):
    """
    Беседа: личная переписка двух пользователей либо системная лента одного пользователя.

    dedupe_key гарантирует отсутствие дублей на уровне БД: для личной беседы —
    отсортированная пара id участников, для системной — id единственного
    пользователя. Формируется сервисом (см. ConversationService), не пользователем.
    """

    kind = models.CharField(
        max_length=16,
        choices=ConversationKind.choices,
        verbose_name="Тип беседы",
    )
    dedupe_key = models.CharField(
        max_length=128,
        unique=True,
        verbose_name="Ключ дедупликации",
        help_text="Например, direct:<id1>:<id2> или system:<user_id>.",
    )
    last_message_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Время последнего сообщения",
    )

    class Meta:
        verbose_name = "Беседа"
        verbose_name_plural = "Беседы"
        ordering = ["-last_message_at", "-created_at"]

    def __str__(self):
        return f"{self.get_kind_display()} #{self.id}"
