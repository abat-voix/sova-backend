from django.db import models

from sova.core.models import TimeStampedModel


class ActionTransition(TimeStampedModel):
    """
    Переход, запускаемый исходом действия — какое действие выполняется дальше.

    Один исход триггерит не более одного перехода (`outcome` — OneToOne), но на одно
    действие-цель может вести несколько переходов от разных исходов/действий.
    """

    active = models.BooleanField(
        default=True,
        verbose_name="Активен",
    )

    outcome = models.OneToOneField(
        to="workflows.ActionOutcome",
        on_delete=models.CASCADE,
        related_name="transition",
        verbose_name="Исход",
    )
    target_action = models.ForeignKey(
        to="workflows.WorkflowAction",
        on_delete=models.CASCADE,
        related_name="action_transitions",
        verbose_name="Целевое действие",
    )

    class Meta:
        verbose_name = "Переход действия"
        verbose_name_plural = "Переходы действий"
        ordering = ["outcome"]

    def __str__(self):
        return f"{self.outcome} → {self.target_action}"
