from django.db import models
from django.db.models import Q

from sova.core.models import TimeStampedModel


class Product(TimeStampedModel):
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
        unique=True,
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

    class Meta:
        verbose_name = "Продукт"
        verbose_name_plural = "Продукты"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["vendor", "name"],
                name="unique_product_per_vendor",
            ),
            models.UniqueConstraint(
                fields=["name"],
                condition=Q(vendor__isnull=True),
                name="unique_product_without_vendor",
            ),
        ]

    def __str__(self):
        return self.name
