from django.db import models
from django.db.models import Q

from sova.core.models import TimeStampedModel


class Interaction(TimeStampedModel):
    """
    Взаимодействие ИТ Школы с вузом либо B2C-клиентом — контрагент ровно один из двух.

    Нейтральна к аудитории: к ней привязан WorkflowInstance, Contract/License опциональны.
    """

    comment = models.TextField(
        blank=True,
        verbose_name="Комментарий",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Активен",
    )

    university = models.ForeignKey(
        to="catalog.University",
        on_delete=models.PROTECT,
        related_name="interactions",
        null=True,
        blank=True,
        verbose_name="Вуз",
    )
    b2c_client = models.ForeignKey(
        to="catalog.B2CClient",
        on_delete=models.PROTECT,
        related_name="interactions",
        null=True,
        blank=True,
        verbose_name="B2C-клиент",
    )

    class Meta:
        verbose_name = "Взаимодействие"
        verbose_name_plural = "Взаимодействия"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                check=(
                    Q(university__isnull=False, b2c_client__isnull=True)
                    | Q(university__isnull=True, b2c_client__isnull=False)
                ),
                name="interaction_exactly_one_counterparty",
            ),
        ]

    def __str__(self):
        return f"Взаимодействие #{self.id} — {self.university or self.b2c_client}"
