from django.conf import settings
from django.db import models

from sova.core.models import TimeStampedModel


class ConversationParticipant(TimeStampedModel):
    """Участие пользователя в беседе и отметка о прочтении."""

    conversation = models.ForeignKey(
        to="messaging.Conversation",
        on_delete=models.CASCADE,
        related_name="participants",
        verbose_name="Беседа",
    )
    user = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="conversation_participations",
        verbose_name="Пользователь",
    )
    last_read_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Прочитано по",
        help_text="Сообщения беседы с created_at не позже этой отметки считаются прочитанными.",
    )

    class Meta:
        verbose_name = "Участник беседы"
        verbose_name_plural = "Участники беседы"
        constraints = [
            models.UniqueConstraint(
                fields=["conversation", "user"],
                name="unique_conversation_participant",
            ),
        ]

    def __str__(self):
        return f"{self.user} в беседе #{self.conversation_id}"
