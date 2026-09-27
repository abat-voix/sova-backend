from django.db import models

from sova.core.models import NormalizedTextFieldsMixin, TimeStampedModel


class Program(NormalizedTextFieldsMixin, TimeStampedModel):
    """
    Программа — учебный курс целиком (методические материалы, практика, расписание)
    по одному направлению. Продуктозависимость не хранится отдельным полем — она
    выводится из наличия связанных Product.
    """

    name = models.CharField(
        max_length=255,
        verbose_name="Название программы",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Активна",
    )

    direction = models.ForeignKey(
        to="catalog.Direction",
        on_delete=models.PROTECT,
        related_name="programs",
        verbose_name="Направление",
    )

    normalized_text_fields = ("name",)

    class Meta:
        verbose_name = "Программа"
        verbose_name_plural = "Программы"
        ordering = ["name"]

    def __str__(self):
        return self.name
