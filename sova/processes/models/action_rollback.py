from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from sova.core.models import UUIDModel


class ActionRollback(UUIDModel):
    """
    Запись журнала об откате действия: кто, когда и по какой причине откатил выполненное действие.

    Журнал — история, а не состояние: сам откат выполняет сервис, а запись хранит только факт.
    Прежний результат откатываемого исполнения остаётся в ActionResult и ActionInstance.
    """

    reason = models.TextField(
        verbose_name="Причина",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания",
    )

    workflow_instance = models.ForeignKey(
        to="processes.WorkflowInstance",
        on_delete=models.CASCADE,
        related_name="action_rollbacks",
        verbose_name="Процесс workflow",
    )
    stage_instance = models.ForeignKey(
        to="processes.StageInstance",
        on_delete=models.CASCADE,
        related_name="action_rollbacks",
        verbose_name="Экземпляр этапа",
    )
    from_action_instance = models.ForeignKey(
        to="processes.ActionInstance",
        on_delete=models.CASCADE,
        related_name="rollbacks_as_cancelled",
        verbose_name="Отменённое исполнение",
    )
    to_action_instance = models.ForeignKey(
        to="processes.ActionInstance",
        on_delete=models.CASCADE,
        related_name="rollbacks_as_target",
        verbose_name="Новое исполнение",
    )
    created_by = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="action_rollbacks",
        null=True,
        blank=True,
        verbose_name="Создал",
    )

    class Meta:
        verbose_name = "Откат действия"
        verbose_name_plural = "Откаты действий"
        ordering = ["-created_at"]

    def clean(self):
        if self.from_action_instance.stage_instance_id != self.stage_instance_id:
            raise ValidationError(
                {"from_action_instance": "Действие относится к другому этапу."}
            )
        if self.to_action_instance.stage_instance_id != self.stage_instance_id:
            raise ValidationError(
                {"to_action_instance": "Действие относится к другому этапу."}
            )
        if self.from_action_instance_id == self.to_action_instance_id:
            raise ValidationError(
                {"to_action_instance": "Новое исполнение не может совпадать с отменённым."}
            )

    def __str__(self):
        return f"{self.from_action_instance} → {self.to_action_instance}"
