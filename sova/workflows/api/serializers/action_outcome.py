from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.workflows.api.serializers.workflow_action import WorkflowActionShortSerializer
from sova.workflows.models import ActionOutcome


class ActionOutcomeShortSerializer(serializers.ModelSerializer):
    """Исход действия — краткое представление для вложенного использования."""

    class Meta:
        model = ActionOutcome
        fields = ("id", "code", "name")


class ActionOutcomeSerializer(serializers.ModelSerializer):
    """Исход действия — представление для чтения (list/retrieve)."""

    action = WorkflowActionShortSerializer(
        read_only=True,
        label=_("Действие"),
        help_text=_("Показывается развёрнуто, для записи см. write-сериализатор"),
    )

    class Meta:
        model = ActionOutcome
        fields = (
            "id",
            "code",
            "name",
            "active",
            "comment_required",
            "attachment_required",
            "action",
            "created_at",
            "updated_at",
        )


class WriteActionOutcomeSerializer(serializers.ModelSerializer):
    """Исход действия — валидация входных данных (create/update)."""

    class Meta:
        model = ActionOutcome
        fields = (
            "id",
            "code",
            "name",
            "active",
            "comment_required",
            "attachment_required",
            "action",
        )
