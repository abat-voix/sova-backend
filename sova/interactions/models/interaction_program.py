from django.db import models

from sova.core.models import UUIDModel


class InteractionProgram(UUIDModel):
    """
    Программа в рамках конкретного взаимодействия.

    Направление программы не дублируется отдельным FK — оно выводится через
    `program.direction` (Program.direction обязателен в каталоге).
    """

    added_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Добавлена",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Активна",
    )

    interaction = models.ForeignKey(
        to="interactions.Interaction",
        on_delete=models.CASCADE,
        related_name="interaction_programs",
        verbose_name="Взаимодействие",
    )
    program = models.ForeignKey(
        to="catalog.Program",
        on_delete=models.PROTECT,
        related_name="interaction_programs",
        verbose_name="Программа",
    )

    class Meta:
        verbose_name = "Программа взаимодействия"
        verbose_name_plural = "Программы взаимодействия"
        ordering = ["interaction", "added_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["interaction", "program"],
                name="unique_program_per_interaction",
            ),
        ]

    def __str__(self):
        return f"{self.interaction} — {self.program}"
