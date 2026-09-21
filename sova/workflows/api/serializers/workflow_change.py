from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.core.api.serializers import UserShortSerializer
from sova.workflows.models import WorkflowChange


class WorkflowChangeSerializer(serializers.ModelSerializer):
    """Изменение workflow (аудит) — представление для чтения."""

    created_by = UserShortSerializer(
        read_only=True,
        label=_("Создал"),
        help_text=_("Пользователь, внёсший изменение; пусто, если он удалён"),
    )

    class Meta:
        model = WorkflowChange
        fields = (
            "id",
            "change_type",
            "entity_type",
            "entity_id",
            "workflow",
            "created_by",
            "created_at",
        )
