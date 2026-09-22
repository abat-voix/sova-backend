from django.db import models

from sova.core.models import TimeStampedModel
from sova.workflows.enum import ActionFeatureCode


class ActionFeature(TimeStampedModel):
    """Возможность, настроенная у шаблонного действия workflow."""

    action = models.ForeignKey("workflows.WorkflowAction", on_delete=models.CASCADE, related_name="features")
    code = models.CharField(max_length=100, choices=ActionFeatureCode.choices)
    sort_order = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    settings = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["sort_order"]
        constraints = [
            models.UniqueConstraint(fields=["action", "code"], name="unique_action_feature_code"),
            models.UniqueConstraint(fields=["action", "sort_order"], name="unique_action_feature_order"),
        ]

    def __str__(self):
        return f"{self.action}: {self.code}"
