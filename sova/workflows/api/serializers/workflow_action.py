from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.workflows.api.serializers.workflow_stage import WorkflowStageShortSerializer
from sova.workflows.models import WorkflowAction
from sova.workflows.services import action_dependency_service


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
            "is_trigger_only",
            "is_active",
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
            "is_trigger_only",
            "is_active",
            "stage",
        )

    def validate(self, attrs: dict) -> dict:
        """
        Защита правил графа при правке существующего действия.

        Перенос в другой этап и смена признака обязательности могут нарушить связи, которые
        создавались с проверками: зависимости и переходы — только внутри этапа, обязательное
        действие не ждёт необязательное.
        """
        if self.instance is None:
            return attrs
        stage = attrs.get("stage", self.instance.stage)
        if stage.pk != self.instance.stage_id and action_dependency_service.has_active_links(
            action=self.instance,
        ):
            raise serializers.ValidationError(
                {
                    "stage": _(
                        "У действия есть активные зависимости или переходы — перенос в другой этап нарушил бы их. "
                        "Сначала отключите или удалите связи.",
                    ),
                },
            )
        is_optional = attrs.get("is_optional", self.instance.is_optional)
        if is_optional and not self.instance.is_optional:
            if action_dependency_service.has_mandatory_dependents(action=self.instance):
                raise serializers.ValidationError(
                    {"is_optional": _("От действия зависят обязательные действия — оно не может быть необязательным.")},
                )
        if not is_optional and self.instance.is_optional:
            if action_dependency_service.waits_for_optional(action=self.instance):
                raise serializers.ValidationError(
                    {"is_optional": _("Действие ждёт необязательное действие — оно не может быть обязательным.")},
                )
        return attrs
