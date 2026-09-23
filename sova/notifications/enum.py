from django.db.models import TextChoices


class NotificationChannel(TextChoices):
    """Канал доставки уведомления."""

    EMAIL = "email", "Email"
    TELEGRAM = "telegram", "Telegram"
    MAX = "max", "MAX"
