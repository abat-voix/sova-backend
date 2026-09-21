from django.db import models

from sova.core.models import UUIDModel


class InteractionDirection(UUIDModel):
    """
    Направление в рамках конкретного взаимодействия.

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
        verbose_name="Взаимодействие",
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
            models.UniqueConstraint(
                fields=["interaction", "direction"],
                name="unique_direction_per_interaction",
            ),
        ]

    def __str__(self):
        return f"{self.interaction} — {self.direction}"
