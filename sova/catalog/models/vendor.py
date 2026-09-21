from django.db import models

from sova.core.models import TimeStampedModel


class Vendor(TimeStampedModel):
    """Вендор продукта (например, 1С, JetBrains)."""

    name = models.CharField(
        max_length=255,
        unique=True,
        verbose_name="Название вендора",
    )
    external_code = models.CharField(
        max_length=255,
        unique=True,
        null=True,
        blank=True,
        verbose_name="Внешний идентификатор",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Активен",
    )

    class Meta:
        verbose_name = "Вендор"
        verbose_name_plural = "Вендоры"
        ordering = ["name"]

    def __str__(self):
        return self.name
