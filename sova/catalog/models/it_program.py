from django.db import models

from sova.core.models import TimeStampedModel


class ITProgram(TimeStampedModel):
    """
    ИТ-программа — учебный курс целиком (методические материалы, практика, расписание)
    по одному ИТ-направлению. Продуктозависимость не хранится отдельным полем — она
    выводится из наличия связанных ITProduct.
    """

    name = models.CharField(
        max_length=255,
        verbose_name="Название программы",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Активна",
    )

    it_direction = models.ForeignKey(
        to="catalog.ITDirection",
        on_delete=models.PROTECT,
        related_name="it_programs",
        verbose_name="ИТ-направление",
    )

    class Meta:
        verbose_name = "ИТ-программа"
        verbose_name_plural = "ИТ-программы"
        ordering = ["name"]

    def __str__(self):
        return self.name
