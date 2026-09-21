from django.conf import settings
from django.db import models

from sova.core.models import UUIDModel


class WorkflowChange(UUIDModel):
    """Аудит изменений определения workflow (кто/когда/что поменял в структуре графа)."""

    change_type = models.CharField(
        max_length=50,
        verbose_name="Тип изменения",
    )
    entity_type = models.CharField(
        max_length=50,
        verbose_name="Тип сущности",
    )
    entity_id = models.UUIDField(
        verbose_name="ID сущности",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания",
    )

    workflow = models.ForeignKey(
        to="workflows.Workflow",
        on_delete=models.CASCADE,
        related_name="workflow_changes",
        verbose_name="Workflow",
    )
    created_by = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="workflow_changes",
        null=True,
        blank=True,
        verbose_name="Создал",
    )

    class Meta:
        verbose_name = "Изменение workflow"
        verbose_name_plural = "Изменения workflow"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.workflow} — {self.change_type} {self.entity_type}"
