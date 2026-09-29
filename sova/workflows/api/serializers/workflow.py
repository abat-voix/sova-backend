from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.core.api.serializers import UserShortSerializer
from sova.workflows.models import Workflow


class WorkflowShortSerializer(serializers.ModelSerializer):
    """Workflow — краткое представление для вложенного использования."""

    class Meta:
        model = Workflow
        fields = ("id", "name", "code")


class WorkflowSerializer(serializers.ModelSerializer):
    """Workflow — представление для чтения (list/retrieve)."""

    created_by = UserShortSerializer(
        read_only=True,
        label=_("Создал"),
        help_text=_("Автор шаблона; пусто, если пользователь удалён"),
    )
    stages_count = serializers.IntegerField(
        read_only=True,
        label=_("Количество этапов"),
        help_text=_("Считается через annotate() на стороне ViewSet"),
    )

    class Meta:
        model = Workflow
        fields = (
            "id",
            "name",
            "code",
            "audience",
            "description",
            "stale_threshold_days",
            "is_base",
            "is_active",
            "created_by",
            "created_at",
            "updated_at",
            "stages_count",
        )


class WriteWorkflowSerializer(serializers.ModelSerializer):
    """Workflow — валидация входных данных (create/update)."""

    class Meta:
        model = Workflow
        fields = (
            "id",
            "name",
            "code",
            "audience",
            "description",
            "stale_threshold_days",
            "is_base",
            "is_active",
        )
