from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from sova.core.models import UUIDModel
from sova.processes.enum import RollbackMode


class StageRollback(UUIDModel):
    """
    Запись журнала об откате: кто, когда и по какой причине отменил этап и на какой этап вернул процесс.

    Журнал — история, а не состояние: сам откат выполняет сервис, а запись хранит только факт.
    Прежние результаты действий откатываемых этапов остаются в ActionResult и ActionInstance.
    """

    reason = models.TextField(
        verbose_name="Причина",
    )
    mode = models.CharField(
        max_length=20,
        choices=RollbackMode.choices,
        verbose_name="Режим",
        help_text=(
            "Как возвращается этап, на который вернулся процесс: заново целиком "
            "или только последнее обязательное действие."
        ),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания",
    )

    workflow_instance = models.ForeignKey(
        to="processes.WorkflowInstance",
        on_delete=models.CASCADE,
        related_name="stage_rollbacks",
        verbose_name="Процесс workflow",
    )
    from_stage_instance = models.ForeignKey(
        to="processes.StageInstance",
        on_delete=models.CASCADE,
        related_name="rollbacks_as_cancelled",
        verbose_name="Отменённый этап",
    )
    to_stage_instance = models.ForeignKey(
        to="processes.StageInstance",
        on_delete=models.CASCADE,
        related_name="rollbacks_as_target",
        verbose_name="Этап возврата",
    )
    created_by = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="stage_rollbacks",
        null=True,
        blank=True,
        verbose_name="Создал",
    )

    class Meta:
        verbose_name = "Откат этапа"
        verbose_name_plural = "Откаты этапов"
        ordering = ["-created_at"]

    def clean(self):
        if self.from_stage_instance.workflow_instance_id != self.workflow_instance_id:
            raise ValidationError(
                {"from_stage_instance": "Этап относится к другому процессу workflow."}
            )
        if self.to_stage_instance.workflow_instance_id != self.workflow_instance_id:
            raise ValidationError(
                {"to_stage_instance": "Этап относится к другому процессу workflow."}
            )
        if self.from_stage_instance_id == self.to_stage_instance_id:
            raise ValidationError(
                {"to_stage_instance": "Процесс нельзя вернуть на тот же этап."}
            )

    def __str__(self):
        return f"{self.from_stage_instance} → {self.to_stage_instance}"
