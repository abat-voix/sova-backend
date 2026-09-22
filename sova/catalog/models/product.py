from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower

from sova.core.models import NormalizedTextFieldsMixin, TimeStampedModel


class Product(NormalizedTextFieldsMixin, TimeStampedModel):
    """
    Продукт — ПО, помогающее в обучении.

    Связан с направлением транзитивно через Program.direction, а не напрямую.
    """

    name = models.CharField(
        max_length=255,
        verbose_name="Название продукта",
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

    vendor = models.ForeignKey(
        to="catalog.Vendor",
        on_delete=models.SET_NULL,
        related_name="products",
        null=True,
        blank=True,
        verbose_name="Вендор",
    )
    programs = models.ManyToManyField(
        to="catalog.Program",
        related_name="products",
        blank=True,
        verbose_name="Программы",
    )

    normalized_text_fields = ("name", "external_code")

    class Meta:
        verbose_name = "Продукт"
        verbose_name_plural = "Продукты"
        ordering = ["name"]
        # Название (в паре с вендором) и код уникальны без учёта регистра: импорт сопоставляет их через iexact.
        constraints = [
            models.UniqueConstraint(
                F("vendor"),
                Lower("name"),
                name="unique_product_per_vendor",
                violation_error_message="Продукт с таким названием у этого вендора уже существует.",
            ),
            models.UniqueConstraint(
                Lower("name"),
                condition=Q(vendor__isnull=True),
                name="unique_product_without_vendor",
                violation_error_message="Продукт с таким названием без вендора уже существует.",
            ),
            models.UniqueConstraint(
                Lower("external_code"),
                name="unique_product_external_code_ci",
                violation_error_message="Продукт с таким внешним идентификатором уже существует.",
            ),
        ]

    def __str__(self):
        return self.name
