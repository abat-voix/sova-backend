from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.workflows.api.serializers.workflow_stage import WorkflowStageShortSerializer
from sova.workflows.models import WorkflowAction


class WorkflowActionShortSerializer(serializers.ModelSerializer):
    """Действие workflow — краткое представление для вложенного использования."""

    class Meta:
        model = WorkflowAction
        fields = ("id", "name")


class WorkflowActionSerializer(serializers.ModelSerializer):
    """Действие workflow — представление для чтения (list/retrieve)."""

    stage = WorkflowStageShortSerializer(
        read_only=True,
        label=_("Этап"),
        help_text=_("Показывается развёрнуто, для записи см. write-сериализатор"),
    )

    class Meta:
        model = WorkflowAction
        fields = (
            "id",
            "name",
            "description",
            "sort_order",
            "default_duration_days",
            "is_optional",
            "active",
            "stage",
            "created_at",
            "updated_at",
        )


class WriteWorkflowActionSerializer(serializers.ModelSerializer):
    """Действие workflow — валидация входных данных (create/update)."""

    class Meta:
        model = WorkflowAction
        fields = (
            "id",
            "name",
            "description",
            "sort_order",
            "default_duration_days",
            "is_optional",
            "active",
            "stage",
        )
