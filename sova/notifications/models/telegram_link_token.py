from django.conf import settings
from django.db import models
from django.utils import timezone

from sova.core.models import TimeStampedModel


class TelegramLinkToken(TimeStampedModel):
    """
    Одноразовый токен привязки Telegram-аккаунта к пользователю СОВА.

    Выдаётся по запросу «Подключить Telegram» и кодируется в deep-ссылку
    `https://t.me/<бот>?start=<id>`. Погашается Telegram-ботом после успешной
    привязки (`used_at`) либо истекает по `expires_at`.
    """

    user = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="telegram_link_tokens",
        verbose_name="Пользователь",
    )
    expires_at = models.DateTimeField(verbose_name="Действителен до")
    used_at = models.DateTimeField(null=True, blank=True, verbose_name="Использован")

    class Meta:
        verbose_name = "Токен привязки Telegram"
        verbose_name_plural = "Токены привязки Telegram"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} — {self.id}"

    @property
    def is_valid(self) -> bool:
        """Токен ещё не использован и не просрочен."""
        return self.used_at is None and self.expires_at > timezone.now()

    def mark_used(self) -> None:
        """Погашает токен, чтобы его нельзя было применить повторно."""
        self.used_at = timezone.now()
        self.save(update_fields=["used_at"])
