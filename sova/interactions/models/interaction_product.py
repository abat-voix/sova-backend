from django.core.exceptions import ValidationError
from django.db import models

from sova.core.models import UUIDModel


class InteractionProduct(UUIDModel):
    """
    Продукт в рамках конкретного взаимодействия.

    `interaction_program` пуст, если продукт добавлен вне привязки к программе: в каталоге
    Product.programs может быть пустым, а состав продуктов договора расширяется со временем.
    """

    added_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Добавлен",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Активен",
    )

    interaction = models.ForeignKey(
        to="interactions.Interaction",
        on_delete=models.CASCADE,
        related_name="interaction_products",
        verbose_name="Взаимодействие",
    )
    interaction_program = models.ForeignKey(
        to="interactions.InteractionProgram",
        on_delete=models.PROTECT,
        related_name="interaction_products",
        null=True,
        blank=True,
        verbose_name="Программа взаимодействия",
        help_text="Пусто — продукт добавлен вне привязки к программе.",
    )
    product = models.ForeignKey(
        to="catalog.Product",
        on_delete=models.PROTECT,
        related_name="interaction_products",
        verbose_name="Продукт",
    )

    class Meta:
        verbose_name = "Продукт взаимодействия"
        verbose_name_plural = "Продукты взаимодействия"
        ordering = ["interaction", "added_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["interaction", "product"],
                name="unique_product_per_interaction",
            ),
        ]

    def clean(self):
        program = self.interaction_program
        if program is None:
            return
        if program.interaction_id != self.interaction_id:
            raise ValidationError(
                {"interaction_program": "Программа принадлежит другому взаимодействию."}
            )
        if not program.program.products.filter(pk=self.product_id).exists():
            raise ValidationError(
                {"product": "Продукт не входит в каталог выбранной программы."}
            )

    def __str__(self):
        return f"{self.interaction} — {self.product}"
