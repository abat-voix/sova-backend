import uuid

from django.db import models


class UUIDModel(models.Model):
    """Базовая модель со суррогатным uuid PK."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        verbose_name="ID",
    )

    class Meta:
        abstract = True


class TimeStampedModel(UUIDModel):
    """Базовая модель с uuid PK и стандартными аудит-полями created_at/updated_at."""

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления",
    )

    class Meta:
        abstract = True
