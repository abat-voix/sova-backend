from django.db import models
from django.db.models.functions import Lower

from sova.core.models import NormalizedTextFieldsMixin, TimeStampedModel


class Vendor(NormalizedTextFieldsMixin, TimeStampedModel):
    """Вендор продукта (например, 1С, JetBrains)."""

    name = models.CharField(
        max_length=255,
        verbose_name="Название вендора",
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
        verbose_name = "Вендор"
        verbose_name_plural = "Вендоры"
        ordering = ["name"]
        # Название и код уникальны без учёта регистра: импорт сопоставляет их через iexact.
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                name="unique_vendor_name_ci",
                violation_error_message="Вендор с таким названием уже существует.",
            ),
            models.UniqueConstraint(
                Lower("external_code"),
                name="unique_vendor_external_code_ci",
                violation_error_message="Вендор с таким внешним идентификатором уже существует.",
            ),
        ]

    def __str__(self):
        return self.name
