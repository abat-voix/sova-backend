from django.conf import settings
from django.db import models
from django.db.models import Q

from sova.core.models import TimeStampedModel
from sova.messaging.enum import ConversationKind


class Conversation(TimeStampedModel):
    """
    Беседа: личная переписка двух пользователей, системная лента одного
    пользователя либо чат Взаимодействия.

    dedupe_key гарантирует отсутствие дублей на уровне БД: для личной беседы —
    отсортированная пара id участников, для системной — id единственного
    пользователя, для чата Взаимодействия — id Взаимодействия. Формируется
    сервисом (см. ConversationService), не пользователем.
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
        help_text="Например, direct:<id1>:<id2>, system:<user_id> или interaction:<interaction_id>.",
    )
    interaction = models.OneToOneField(
        to="interactions.Interaction",
        on_delete=models.CASCADE,
        related_name="chat",
        null=True,
        blank=True,
        verbose_name="Взаимодействие",
        help_text="Заполнено только у чата типа interaction; удаление Взаимодействия удаляет и чат.",
    )
    created_by = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="+",
        null=True,
        blank=True,
        verbose_name="Создатель",
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
        constraints = [
            models.CheckConstraint(
                check=(
                    Q(kind=ConversationKind.INTERACTION, interaction__isnull=False)
                    | (~Q(kind=ConversationKind.INTERACTION) & Q(interaction__isnull=True))
                ),
                name="interaction_conversation_requires_interaction",
            ),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} #{self.id}"
