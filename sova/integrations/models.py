import uuid

from django.db import models

from sova.core.models import TimeStampedModel
from sova.integrations.enum import IntegrationDirection, IntegrationStatus


class IntegrationMapping(TimeStampedModel):
    """A versioned, administrator-managed payload mapping."""

    name = models.CharField(max_length=255, verbose_name="Название")
    system = models.CharField(max_length=50, verbose_name="Система")
    event_type = models.CharField(max_length=100, verbose_name="Тип события")
    direction = models.CharField(
        max_length=8, choices=IntegrationDirection.choices, verbose_name="Направление"
    )
    entity = models.CharField(max_length=100, verbose_name="Сущность CRM")
    is_active = models.BooleanField(default=False, verbose_name="Активен")
    version = models.PositiveIntegerField(default=1, verbose_name="Версия")
    rules = models.JSONField(default=list, verbose_name="Правила")

    class Meta:
        verbose_name = "маппинг интеграции"
        verbose_name_plural = "маппинги интеграций"
        ordering = ("-updated_at", "name")

    def __str__(self):
        return self.name


class IntegrationMessage(TimeStampedModel):
    system = models.CharField(max_length=50, verbose_name="Система")
    direction = models.CharField(
        max_length=8, choices=IntegrationDirection.choices, verbose_name="Направление"
    )
    event_type = models.CharField(max_length=100, default="generic.received", verbose_name="Тип события")
    external_id = models.CharField(max_length=255, blank=True, verbose_name="Внешний ID")
    correlation_id = models.UUIDField(default=uuid.uuid4, verbose_name="Correlation ID")
    payload = models.JSONField(verbose_name="Payload")
    status = models.CharField(
        max_length=16,
        choices=IntegrationStatus.choices,
        default=IntegrationStatus.PENDING,
        verbose_name="Статус",
    )
    attempts = models.PositiveSmallIntegerField(default=0, verbose_name="Попыток")
    next_retry_at = models.DateTimeField(null=True, blank=True, verbose_name="Следующая попытка")
    last_error = models.TextField(blank=True, verbose_name="Последняя ошибка")
    processed_at = models.DateTimeField(null=True, blank=True, verbose_name="Обработано")

    class Meta:
        verbose_name = "Интеграционное сообщение"
        verbose_name_plural = "Интеграционные сообщения"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["system", "direction", "external_id"],
                condition=~models.Q(external_id=""),
                name="integration_message_external_id_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["status", "next_retry_at"], name="integration_status_retry_idx"),
            models.Index(fields=["system", "direction", "created_at"], name="integration_system_dir_idx"),
            models.Index(fields=["correlation_id"], name="integration_correlation_idx"),
        ]

    def __str__(self):
        return f"{self.system}:{self.event_type} ({self.get_status_display()})"
