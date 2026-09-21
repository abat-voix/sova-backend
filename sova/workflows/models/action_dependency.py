from django.db import models

from sova.core.models import TimeStampedModel


class ActionDependency(TimeStampedModel):
    """Зависимость действия от другого действия того же workflow (граф для непоследовательных шагов)."""

    is_active = models.BooleanField(
        default=True,
        verbose_name="Активна",
    )

    action = models.ForeignKey(
        to="workflows.WorkflowAction",
        on_delete=models.CASCADE,
        related_name="action_dependencies_as_action",
        verbose_name="Действие",
    )
    depends_on_action = models.ForeignKey(
        to="workflows.WorkflowAction",
        on_delete=models.CASCADE,
        related_name="action_dependencies_as_depends_on_action",
        verbose_name="Зависит от действия",
    )

    class Meta:
        verbose_name = "Зависимость действия"
        verbose_name_plural = "Зависимости действий"
        ordering = ["action", "depends_on_action"]
        constraints = [
            models.UniqueConstraint(
                fields=["action", "depends_on_action"],
                name="unique_action_dependency",
            ),
            models.CheckConstraint(
                check=~models.Q(action=models.F("depends_on_action")),
                name="action_dependency_no_self_reference",
            ),
        ]

    def __str__(self):
        return f"{self.action} ⊐ {self.depends_on_action}"
