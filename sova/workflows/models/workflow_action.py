from django.db import models

from sova.core.models import TimeStampedModel


class WorkflowAction(TimeStampedModel):
    """Действие внутри этапа workflow."""

    name = models.CharField(
        max_length=255,
        verbose_name="Название",
    )
    description = models.TextField(
        blank=True,
        verbose_name="Описание",
    )
    sort_order = models.PositiveIntegerField(
        verbose_name="Порядковый номер",
    )
    default_duration_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Плановая длительность, дней",
        help_text=(
            "Используется и как план (planned_end = planned_start + default_duration_days), "
            "и как порог контроля зависания действия. NULL — контроль зависания не ведётся."
        ),
    )
    is_optional = models.BooleanField(
        default=False,
        verbose_name="Можно пропустить без исхода",
    )
    active = models.BooleanField(
        default=True,
        verbose_name="Активно",
    )

    stage = models.ForeignKey(
        to="workflows.WorkflowStage",
        on_delete=models.CASCADE,
        related_name="workflow_actions",
        verbose_name="Этап",
    )

    class Meta:
        verbose_name = "Действие workflow"
        verbose_name_plural = "Действия workflow"
        ordering = ["stage", "sort_order"]
        constraints = [
            models.UniqueConstraint(
                fields=["stage", "sort_order"],
                name="unique_stage_action_order",
            ),
        ]

    def __str__(self):
        return self.name
