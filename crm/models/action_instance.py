from django.conf import settings
from django.db import models

from crm.models.base import UUIDModel


class ActionInstance(UUIDModel):
    """
    Экземпляр действия workflow. `action_name_snapshot` фиксирует имя действия на момент
    исполнения — не зависит от последующих правок определения workflow.
    """

    action_name_snapshot = models.CharField(
        max_length=255,
        verbose_name="Название действия (слепок)",
    )
    status = models.CharField(
        max_length=50,
        verbose_name="Статус",
    )
    planned_start = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Плановое начало",
    )
    planned_end = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Плановое окончание",
    )
    actual_start = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Фактическое начало",
    )
    actual_end = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Фактическое окончание",
    )
    execution_no = models.PositiveIntegerField(
        default=1,
        verbose_name="Номер исполнения",
    )

    stage_instance = models.ForeignKey(
        to="crm.StageInstance",
        on_delete=models.CASCADE,
        related_name="action_instances",
        verbose_name="Экземпляр этапа",
    )
    action = models.ForeignKey(
        to="crm.WorkflowAction",
        on_delete=models.PROTECT,
        related_name="action_instances",
        verbose_name="Действие",
    )
    responsible = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="action_instances",
        null=True,
        blank=True,
        verbose_name="Ответственный",
    )

    class Meta:
        verbose_name = "Экземпляр действия"
        verbose_name_plural = "Экземпляры действий"
        ordering = ["stage_instance", "planned_start"]

    def __str__(self):
        return self.action_name_snapshot
