from django.db.models import TextChoices


class IntegrationDirection(TextChoices):
    INCOMING = "incoming", "Входящее"
    OUTGOING = "outgoing", "Исходящее"


class IntegrationStatus(TextChoices):
    PENDING = "pending", "Ожидает обработки"
    PROCESSING = "processing", "Обрабатывается"
    PROCESSED = "processed", "Обработано"
    RETRY = "retry", "Повтор"
    FAILED = "failed", "Ошибка"
    IGNORED = "ignored", "Игнорировано"
