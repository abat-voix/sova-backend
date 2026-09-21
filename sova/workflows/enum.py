from django.db.models import TextChoices


class Audience(TextChoices):
    """Целевая аудитория workflow-шаблона."""

    B2B = "b2b", "Вузы"
    B2C = "b2c", "Физ/юрлица"


class WorkflowChangeType(TextChoices):
    """Тип изменения определения workflow в аудите."""

    CREATED = "created", "Создано"
    UPDATED = "updated", "Изменено"
    DELETED = "deleted", "Удалено"
