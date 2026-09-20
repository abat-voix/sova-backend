from django.core.exceptions import ValidationError
from django.db import models

from sova.core.models import TimeStampedModel


class StageTransition(TimeStampedModel):
    """
    Связь между этапами: этап-цель открывается после закрытия этапа-источника.

    Безусловная — следующий этап не выбирается по исходу действий. Если в этап ведёт несколько
    связей, он открывается, когда закрыты все этапы-источники. Этап без входящих связей открывается
    при старте процесса. Он же служит основой отката: «предыдущий» этап — источник входящей связи.
    Циклы запрещены, но проверяются на уровне API (модель проверяет только пару этапов).

    Источник и цель могут быть разных типов (в том числе цель — этап взаимодействия после этапа
    направления, программы или продукта): движок в этом случае ждёт закрытия всех действующих
    экземпляров этапа-источника, а не одного — см. `WorkflowEngineService._source_instances`.
    """

    active = models.BooleanField(
        default=True,
        verbose_name="Активна",
    )

    from_stage = models.ForeignKey(
        to="workflows.WorkflowStage",
        on_delete=models.CASCADE,
        related_name="stage_transitions_as_from_stage",
        verbose_name="Этап-источник",
    )
    to_stage = models.ForeignKey(
        to="workflows.WorkflowStage",
        on_delete=models.CASCADE,
        related_name="stage_transitions_as_to_stage",
        verbose_name="Этап-цель",
    )

    class Meta:
        verbose_name = "Связь этапов"
        verbose_name_plural = "Связи этапов"
        ordering = ["from_stage", "to_stage"]
        constraints = [
            models.UniqueConstraint(
                fields=["from_stage", "to_stage"],
                name="unique_stage_transition",
            ),
            models.CheckConstraint(
                check=~models.Q(from_stage=models.F("to_stage")),
                name="stage_transition_no_self_reference",
            ),
        ]

    def clean(self):
        if self.from_stage.workflow_id != self.to_stage.workflow_id:
            raise ValidationError(
                {"to_stage": "Этап-цель относится к другому workflow."}
            )

    def __str__(self):
        return f"{self.from_stage} → {self.to_stage}"
