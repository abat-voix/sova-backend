from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.core.api.serializers import UserShortSerializer
from sova.processes.models import StageInstance
from sova.workflows.api.serializers import WorkflowStageShortSerializer


class StageInstanceShortSerializer(serializers.ModelSerializer):
    """Экземпляр этапа — краткое представление для вложенного использования."""

    stage = WorkflowStageShortSerializer(
        read_only=True,
        label=_("Этап"),
        help_text=_("Показывается развёрнуто, для записи см. write-сериализатор"),
    )

    class Meta:
        model = StageInstance
        fields = ("id", "stage", "context_type", "context_id")


class StageInstanceSerializer(serializers.ModelSerializer):
    """Экземпляр этапа — представление для чтения (list/retrieve)."""

    stage = WorkflowStageShortSerializer(
        read_only=True,
        label=_("Этап"),
        help_text=_("Показывается развёрнуто, для записи см. write-сериализатор"),
    )
    added_by = UserShortSerializer(
        read_only=True,
        label=_("Кто добавил"),
        help_text=_("Пользователь, добавивший этап; пусто, если он удалён"),
    )

    class Meta:
        model = StageInstance
        fields = (
            "id",
            "context_type",
            "context_id",
            "status",
            "added_at",
            "started_at",
            "completed_at",
            "workflow_instance",
            "stage",
            "added_by",
        )
