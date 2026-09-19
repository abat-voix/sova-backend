from django.conf import settings
from django.db import models

from crm.models.base import UUIDModel


class WorkflowInstance(UUIDModel):
    """
    Живой процесс workflow для конкретной сделки.

    Без created_at/updated_at — своя пара дат (started_at/completed_at).
    """

    status = models.CharField(
        max_length=50,
        verbose_name="Статус",
    )
    started_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Начат",
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Завершён",
    )

    workflow = models.ForeignKey(
        to="crm.Workflow",
        on_delete=models.PROTECT,
        related_name="workflow_instances",
        verbose_name="Workflow",
    )
    contact = models.ForeignKey(
        to="crm.Contact",
        on_delete=models.CASCADE,
        related_name="workflow_instances",
        verbose_name="Сделка",
    )
    created_by = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="workflow_instances",
        null=True,
        blank=True,
        verbose_name="Создал",
    )

    class Meta:
        verbose_name = "Процесс workflow"
        verbose_name_plural = "Процессы workflow"
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.workflow} — {self.contact}"
