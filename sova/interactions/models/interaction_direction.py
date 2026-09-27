from django.db import models
from django.db.models import Q

from sova.core.models import UUIDModel


class InteractionDirection(UUIDModel):
    """
    Направление в рамках конкретного взаимодействия либо, до появления Interaction, договора.

    Каталожный Direction общий для всех взаимодействий, поэтому прогресс (StageInstance)
    привязывается не к нему, а к этой записи — уникальной для взаимодействия.
    """

    added_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Добавлено",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Активно",
    )

    interaction = models.ForeignKey(
        to="interactions.Interaction",
        on_delete=models.CASCADE,
        related_name="interaction_directions",
        null=True,
        blank=True,
        verbose_name="Взаимодействие",
    )
    contract = models.ForeignKey(
        to="interactions.Contract",
        on_delete=models.CASCADE,
        related_name="interaction_directions",
        null=True,
        blank=True,
        verbose_name="Договор",
        help_text="Заполнен всегда, если запись пришла из импорта договора; interaction — только "
        "после привязки договора к взаимодействию.",
    )
    direction = models.ForeignKey(
        to="catalog.Direction",
        on_delete=models.PROTECT,
        related_name="interaction_directions",
        verbose_name="Направление",
    )

    class Meta:
        verbose_name = "Направление взаимодействия"
        verbose_name_plural = "Направления взаимодействия"
        ordering = ["interaction", "added_at"]
        constraints = [
            models.CheckConstraint(
                check=Q(interaction__isnull=False) | Q(contract__isnull=False),
                name="interaction_direction_has_owner",
            ),
            models.UniqueConstraint(
                fields=["interaction", "direction"],
                condition=Q(interaction__isnull=False),
                name="unique_direction_per_interaction",
            ),
            models.UniqueConstraint(
                fields=["contract", "direction"],
                condition=Q(contract__isnull=False),
                name="unique_direction_per_contract",
            ),
        ]

    def __str__(self):
        return f"{self.interaction or self.contract} — {self.direction}"
