from django.conf import settings
from django.db import models

from sova.core.models import UUIDModel


class ActionFeatureExecution(UUIDModel):
    """История выполнения feature в конкретном исполнении действия."""

    action_instance = models.ForeignKey(
        "processes.ActionInstance", on_delete=models.CASCADE, related_name="feature_executions",
    )
    feature = models.ForeignKey(
        "workflows.ActionFeature", on_delete=models.PROTECT, related_name="executions",
    )
    feature_code_snapshot = models.CharField(max_length=100)
    target_type = models.CharField(max_length=100)
    target_id = models.UUIDField()
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="action_feature_executions",
    )
    performed_at = models.DateTimeField(auto_now_add=True)
    result = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["performed_at"]

