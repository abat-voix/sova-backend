from django.db import models

from sova.core.models import TimeStampedModel


class ActionOutcome(TimeStampedModel):
    """Возможный исход выполнения действия workflow."""

    code = models.CharField(
        max_length=100,
        verbose_name="Код",
    )
    name = models.CharField(
        max_length=255,
        verbose_name="Название",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Активен",
    )
    is_comment_required = models.BooleanField(
        default=False,
        verbose_name="Требует комментарий",
    )
    is_attachment_required = models.BooleanField(
        default=False,
        verbose_name="Требует вложение",
    )

    action = models.ForeignKey(
        to="workflows.WorkflowAction",
        on_delete=models.CASCADE,
        related_name="action_outcomes",
        verbose_name="Действие",
    )

    class Meta:
        verbose_name = "Исход действия"
        verbose_name_plural = "Исходы действий"
        ordering = ["action", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["action", "code"],
                name="unique_action_outcome_code",
            ),
        ]

    def __str__(self):
        return f"{self.action} — {self.name}"
