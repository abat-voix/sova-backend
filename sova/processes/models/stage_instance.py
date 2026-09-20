from django.apps import apps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from sova.processes.enum import StageInstanceContextType, StageInstanceStatus
from sova.core.models import UUIDModel


class StageInstance(UUIDModel):
    """
    Экземпляр этапа workflow внутри конкретного WorkflowInstance.

    `context_id` — полиморфный указатель (Interaction.id | InteractionDirection.id |
    InteractionProgram.id | InteractionProduct.id в зависимости от context_type), поэтому
    обычным ForeignKey не моделируется. Указывает на записи, уникальные для взаимодействия,
    а не на общий каталог ИТ-направлений/программ/продуктов.
    """

    context_type = models.CharField(
        max_length=20,
        choices=StageInstanceContextType.choices,
        default=StageInstanceContextType.INTERACTION,
        verbose_name="Тип контекста",
    )
    context_id = models.UUIDField(
        null=True,
        blank=True,
        verbose_name="ID контекста",
        help_text=(
            "Указывает на Interaction.id, InteractionDirection.id, InteractionProgram.id "
            "или InteractionProduct.id — по значению context_type."
        ),
    )
    status = models.CharField(
        max_length=50,
        choices=StageInstanceStatus.choices,
        default=StageInstanceStatus.PENDING,
        verbose_name="Статус",
    )
    added_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Добавлен",
    )
    started_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Открыт",
        help_text="Момент, когда этап стал доступен; отличается от момента создания экземпляра (added_at).",
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Завершён",
    )

    workflow_instance = models.ForeignKey(
        to="processes.WorkflowInstance",
        on_delete=models.CASCADE,
        related_name="stage_instances",
        verbose_name="Процесс workflow",
    )
    stage = models.ForeignKey(
        to="workflows.WorkflowStage",
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
        constraints = [
            # Два ограничения вместо одного: NULL в context_id база считает разными значениями,
            # поэтому этап без контекста (взаимодействие целиком) защищаем отдельным условным ограничением
            models.UniqueConstraint(
                fields=["workflow_instance", "stage", "context_type", "context_id"],
                condition=models.Q(context_id__isnull=False),
                name="unique_stage_instance_per_context",
            ),
            models.UniqueConstraint(
                fields=["workflow_instance", "stage", "context_type"],
                condition=models.Q(context_id__isnull=True),
                name="unique_stage_instance_without_context",
            ),
        ]
        indexes = [
            models.Index(
                fields=["context_type", "context_id"],
                name="stage_instance_context_idx",
            ),
        ]

    def clean(self):
        if self.context_id is None:
            return
        if self.context_type == StageInstanceContextType.INTERACTION:
            interaction_id = self.context_id
        else:
            model_name = {
                StageInstanceContextType.IT_DIRECTION: "InteractionDirection",
                StageInstanceContextType.IT_PROGRAM: "InteractionProgram",
                StageInstanceContextType.IT_PRODUCT: "InteractionProduct",
            }[self.context_type]
            context = apps.get_model("interactions", model_name).objects.filter(pk=self.context_id).first()
            if context is None:
                raise ValidationError({"context_id": f"{model_name} с таким ID не найден."})
            interaction_id = context.interaction_id
        if interaction_id != self.workflow_instance.interaction_id:
            raise ValidationError(
                {"context_id": "Контекст относится к другому взаимодействию, чем процесс workflow."}
            )

    def __str__(self):
        return f"{self.workflow_instance} — {self.stage}"
