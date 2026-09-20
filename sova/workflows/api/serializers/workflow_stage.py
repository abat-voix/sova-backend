from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.workflows.api.serializers.workflow import WorkflowShortSerializer
from sova.workflows.models import WorkflowStage


class WorkflowStageShortSerializer(serializers.ModelSerializer):
    """Этап workflow — краткое представление для вложенного использования."""

    class Meta:
        model = WorkflowStage
        fields = ("id", "name", "workflow")


class WorkflowStageSerializer(serializers.ModelSerializer):
    """Этап workflow — представление для чтения (list/retrieve)."""

    workflow = WorkflowShortSerializer(
        read_only=True,
        label=_("Workflow"),
        help_text=_("Показывается развёрнуто, для записи см. write-сериализатор"),
    )

    class Meta:
        model = WorkflowStage
        fields = (
            "id",
            "name",
            "type",
            "description",
            "sort_order",
            "is_initial",
            "is_final",
            "is_optional",
            "active",
            "workflow",
            "created_at",
            "updated_at",
        )


class WriteWorkflowStageSerializer(serializers.ModelSerializer):
    """Этап workflow — валидация входных данных (create/update)."""

    class Meta:
        model = WorkflowStage
        fields = (
            "id",
            "name",
            "type",
            "description",
            "sort_order",
            "is_initial",
            "is_final",
            "is_optional",
            "active",
            "workflow",
        )

    def validate(self, attrs: dict) -> dict:
        """
        Проверка «один начальный этап на workflow».

        Условное ограничение БД `one_initial_stage_per_workflow` DRF не проверяет.
        При PATCH недостающие значения берутся из сохранённого этапа.
        """
        is_initial = attrs.get("is_initial", getattr(self.instance, "is_initial", False))
        workflow = attrs.get("workflow", getattr(self.instance, "workflow", None))
        if not is_initial:
            return attrs

        conflicting = WorkflowStage.objects.filter(workflow=workflow, is_initial=True)
        if self.instance is not None:
            conflicting = conflicting.exclude(pk=self.instance.pk)
        if conflicting.exists():
            raise serializers.ValidationError(
                {"is_initial": _("В этом workflow уже есть начальный этап.")},
            )
        return attrs
