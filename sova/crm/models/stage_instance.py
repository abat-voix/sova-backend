from django.conf import settings
from django.db import models

from sova.crm.enum import StageInstanceContextType
from sova.crm.models.base import UUIDModel


class StageInstance(UUIDModel):
    """
    Экземпляр этапа workflow внутри конкретного WorkflowInstance.

    `context_id` — полиморфный указатель (Contact.id | ITProgram.id | ITProduct.id в
    зависимости от context_type), поэтому обычным ForeignKey не моделируется.
    """

    context_type = models.CharField(
        max_length=20,
        choices=StageInstanceContextType.choices,
        default=StageInstanceContextType.CONTACT,
        verbose_name="Тип контекста",
    )
    context_id = models.UUIDField(
        null=True,
        blank=True,
        verbose_name="ID контекста",
        help_text="Указывает на Contact.id, ITProgram.id или ITProduct.id — по значению context_type.",
    )
    status = models.CharField(
        max_length=50,
        verbose_name="Статус",
    )
    added_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Добавлен",
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Завершён",
    )

    workflow_instance = models.ForeignKey(
        to="crm.WorkflowInstance",
        on_delete=models.CASCADE,
        related_name="stage_instances",
        verbose_name="Процесс workflow",
    )
    stage = models.ForeignKey(
        to="crm.WorkflowStage",
        on_delete=models.PROTECT,
        related_name="stage_instances",
        verbose_name="Этап",
    )
    added_by = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="stage_instances",
        null=True,
        blank=True,
        verbose_name="Кто добавил",
    )

    class Meta:
        verbose_name = "Экземпляр этапа"
        verbose_name_plural = "Экземпляры этапов"
        ordering = ["workflow_instance", "added_at"]

    def __str__(self):
        return f"{self.workflow_instance} — {self.stage}"
