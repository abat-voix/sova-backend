from django.conf import settings
from django.db import models

from sova.crm.models.base import UUIDModel


class ActionResult(UUIDModel):
    """Зафиксированный исход выполненного действия. Запись журнала — не редактируется."""

    outcome_name_snapshot = models.CharField(
        max_length=255,
        verbose_name="Название исхода (слепок)",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания",
    )
    comment = models.TextField(
        blank=True,
        verbose_name="Комментарий",
    )

    action_instance = models.OneToOneField(
        to="crm.ActionInstance",
        on_delete=models.CASCADE,
        related_name="result",
        verbose_name="Экземпляр действия",
    )
    outcome = models.ForeignKey(
        to="crm.ActionOutcome",
        on_delete=models.PROTECT,
        related_name="action_results",
        verbose_name="Исход",
    )
    created_by = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="action_results",
        null=True,
        blank=True,
        verbose_name="Создал",
    )

    class Meta:
        verbose_name = "Результат действия"
        verbose_name_plural = "Результаты действий"
        ordering = ["-created_at"]

    def __str__(self):
        return self.outcome_name_snapshot
