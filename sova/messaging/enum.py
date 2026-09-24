from django.db.models import TextChoices


class ConversationKind(TextChoices):
    """Тип беседы."""

    DIRECT = "direct", "Личная переписка"
    SYSTEM = "system", "Системные сообщения"
