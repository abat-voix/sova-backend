from django.db import models
from django.db.models.functions import Lower

from sova.core.models import NormalizedTextFieldsMixin, TimeStampedModel


class Direction(NormalizedTextFieldsMixin, TimeStampedModel):
    """Направление обучения, например DevOps, QA."""

    name = models.CharField(
        max_length=255,
        verbose_name="Название направления",
    )
    external_code = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="Внешний идентификатор",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Активен",
    )

    normalized_text_fields = ("name", "external_code")

    class Meta:
        verbose_name = "Направление"
        verbose_name_plural = "Направления"
        ordering = ["name"]
        # Название и код уникальны без учёта регистра: импорт сопоставляет их через iexact.
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                name="unique_direction_name_ci",
                violation_error_message="Направление с таким названием уже существует.",
            ),
            models.UniqueConstraint(
                Lower("external_code"),
                name="unique_direction_external_code_ci",
                violation_error_message="Направление с таким внешним идентификатором уже существует.",
            ),
        ]

    def __str__(self):
        return self.name
