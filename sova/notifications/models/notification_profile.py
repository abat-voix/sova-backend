from django.conf import settings
from django.db import models

from sova.core.models import UUIDModel


class NotificationProfile(UUIDModel):
    """
    Контакты пользователя для уведомлений: email, Telegram, MAX.

    Поле email — отдельный адрес для уведомлений, если он должен отличаться
    от user.email (например, логин синхронизируется из Keycloak). Если
    оставлено пустым — используется user.email (см. Recipient.for_user).
    """

    email = models.EmailField(
        blank=True,
        verbose_name="Email для уведомлений",
        help_text="Если не указан — используется email пользователя.",
    )
    telegram_chat_id = models.CharField(
        max_length=64,
        blank=True,
        verbose_name="Telegram chat ID",
    )
    max_chat_id = models.CharField(
        max_length=64,
        blank=True,
        verbose_name="MAX chat ID",
    )

    user = models.OneToOneField(
        to=settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_profile",
        verbose_name="Пользователь",
    )

    class Meta:
        verbose_name = "Профиль уведомлений"
        verbose_name_plural = "Профили уведомлений"
        ordering = ["user_id"]

    def __str__(self):
        return str(self.user)
