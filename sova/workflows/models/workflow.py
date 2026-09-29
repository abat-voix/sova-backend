from django.conf import settings
from django.db import models

from sova.workflows.enum import Audience
from sova.core.models import TimeStampedModel


class Workflow(TimeStampedModel):
    """Шаблон workflow — процесс для одной аудитории (B2B/B2C)."""

    name = models.CharField(
        max_length=255,
        verbose_name="Название",
    )
    code = models.CharField(
        max_length=255,
        unique=True,
        verbose_name="Код",
    )
    audience = models.CharField(
        max_length=10,
        choices=Audience.choices,
        default=Audience.B2B,
        verbose_name="Целевая аудитория процесса",
    )
    description = models.TextField(
        blank=True,
        verbose_name="Описание",
    )
    stale_threshold_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="SLA по заявке целиком, дней",
        help_text=(
            "Считается от WorkflowInstance.started_at — сколько существует вся заявка. "
            "NULL — контроль зависания заявки целиком не ведётся."
        ),
    )
    is_base = models.BooleanField(
        default=False,
        verbose_name="Базовый workflow",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Активен",
    )

    created_by = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="workflows",
        null=True,
        blank=True,
        verbose_name="Создал",
    )

    class Meta:
        verbose_name = "Workflow"
        verbose_name_plural = "Workflow"
        ordering = ["name"]

    def __str__(self):
        return self.name
