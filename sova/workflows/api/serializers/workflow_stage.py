from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.workflows.api.serializers.workflow import WorkflowShortSerializer
from sova.workflows.models import WorkflowStage
from sova.workflows.services import stage_transition_service


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
            "description",
            "sort_order",
            "is_initial",
            "is_final",
            "is_optional",
            "active",
            "workflow",
        )

    def validate(self, attrs: dict) -> dict:
        """Проверка «один начальный этап на workflow» и целостности связей этапа при его правке."""
        self._validate_single_initial(attrs=attrs)
        self._validate_transitions(attrs=attrs)
        return attrs

    def _validate_single_initial(self, attrs: dict) -> None:
        """
        Проверка «один начальный этап на workflow».

        Условное ограничение БД `one_initial_stage_per_workflow` DRF не проверяет.
        При PATCH недостающие значения берутся из сохранённого этапа.
        """
        is_initial = attrs.get("is_initial", getattr(self.instance, "is_initial", False))
        workflow = attrs.get("workflow", getattr(self.instance, "workflow", None))
        if not is_initial:
            return
        conflicting = WorkflowStage.objects.filter(workflow=workflow, is_initial=True)
        if self.instance is not None:
            conflicting = conflicting.exclude(pk=self.instance.pk)
        if conflicting.exists():
            raise serializers.ValidationError(
                {"is_initial": _("В этом workflow уже есть начальный этап.")},
            )

    def _validate_transitions(self, attrs: dict) -> None:
        """
        Защита связей между этапами при правке существующего этапа.

        Связи создавались с проверками (один workflow, допустимые типы этапов), и перенос этапа
        в другой workflow или смена его типа могли бы их нарушить.
        """
        if self.instance is None:
            return
        workflow = attrs.get("workflow", self.instance.workflow)
        if workflow.pk != self.instance.workflow_id and stage_transition_service.has_active_links(
            stage=self.instance,
        ):
            raise serializers.ValidationError(
                {
                    "workflow": _(
                        "У этапа есть активные связи с другими этапами — перенос в другой workflow нарушил бы их. "
                        "Сначала отключите или удалите связи.",
                    ),
                },
            )
        new_type = attrs.get("type", self.instance.type)
        if new_type != self.instance.type and stage_transition_service.conflicts_with_type(
            stage=self.instance,
            new_type=new_type,
        ):
            raise serializers.ValidationError(
                {
                    "type": _(
                        "Смена типа нарушила бы связи этапа: этап взаимодействия не может идти "
                        "после этапа направления, программы или продукта.",
                    ),
                },
            )
