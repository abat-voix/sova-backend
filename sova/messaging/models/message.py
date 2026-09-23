from django.conf import settings
from django.db import models

from sova.core.models import TimeStampedModel


class Message(TimeStampedModel):
    """
    Сообщение в беседе.

    sender пуст для системных сообщений — их создаёт только серверный код
    (см. sova.messaging.services.send_system_message), не пользователь.
    """

    conversation = models.ForeignKey(
        to="messaging.Conversation",
        on_delete=models.CASCADE,
        related_name="messages",
        verbose_name="Беседа",
    )
    sender = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="sent_messages",
        null=True,
        blank=True,
        verbose_name="Отправитель",
    )
    text = models.TextField(verbose_name="Текст")
    link = models.CharField(
        max_length=512,
        blank=True,
        verbose_name="Ссылка",
        help_text="Относительный путь на связанную сущность приложения, если есть.",
    )

    class Meta:
        verbose_name = "Сообщение"
        verbose_name_plural = "Сообщения"
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["conversation", "created_at"], name="messaging_msg_conv_created_idx"),
        ]

    def __str__(self):
        return f"Сообщение #{self.id} в беседе #{self.conversation_id}"
