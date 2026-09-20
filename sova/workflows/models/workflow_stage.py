from django.db import models

from sova.core.models import TimeStampedModel


class WorkflowStage(TimeStampedModel):
    """Этап (шаг) workflow. Точка входа/выхода помечена явным флагом, а не выводится из графа."""

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
    is_initial = models.BooleanField(
        default=False,
        verbose_name="Начальный этап",
    )
    is_final = models.BooleanField(
        default=False,
        verbose_name="Финальный этап",
    )
    is_optional = models.BooleanField(
        default=False,
        verbose_name="Можно пропустить",
    )
    active = models.BooleanField(
        default=True,
        verbose_name="Активен",
    )

    workflow = models.ForeignKey(
        to="workflows.Workflow",
        on_delete=models.CASCADE,
        related_name="workflow_stages",
        verbose_name="Workflow",
    )

    class Meta:
        verbose_name = "Этап workflow"
        verbose_name_plural = "Этапы workflow"
        ordering = ["workflow", "sort_order"]
        constraints = [
            models.UniqueConstraint(
                fields=["workflow", "sort_order"],
                name="unique_workflow_stage_order",
            ),
            models.UniqueConstraint(
                fields=["workflow"],
                condition=models.Q(is_initial=True),
                name="one_initial_stage_per_workflow",
            ),
        ]

    def __str__(self):
        return self.name
