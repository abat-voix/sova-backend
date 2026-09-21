from django.db import models

from sova.core.models import TimeStampedModel


class Direction(TimeStampedModel):
    """Направление обучения, например DevOps, QA."""

    name = models.CharField(
        max_length=255,
        unique=True,
        verbose_name="Название направления",
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
        verbose_name = "Направление"
        verbose_name_plural = "Направления"
        ordering = ["name"]

    def __str__(self):
        return self.name
