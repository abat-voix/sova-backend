from django.db import models
from django.db.models import Q

from crm.models.base import TimeStampedModel


class ITProduct(TimeStampedModel):
    """
    ИТ-продукт — ПО, помогающее в обучении.

    Связан с ИТ-направлением транзитивно через ITProgram.it_direction, а не напрямую.
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
        to="crm.Vendor",
        on_delete=models.SET_NULL,
        related_name="it_products",
        null=True,
        blank=True,
        verbose_name="Вендор",
    )
    programs = models.ManyToManyField(
        to="crm.ITProgram",
        related_name="it_products",
        blank=True,
        verbose_name="ИТ-программы",
    )

    class Meta:
        verbose_name = "ИТ-продукт"
        verbose_name_plural = "ИТ-продукты"
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
