from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.core.api.validators import validate_model_clean
from sova.workflows.api.serializers.workflow_stage import WorkflowStageShortSerializer
from sova.workflows.models import StageTransition
from sova.workflows.services import stage_transition_service


class StageTransitionSerializer(serializers.ModelSerializer):
    """Связь между этапами — представление для чтения (list/retrieve)."""

    from_stage = WorkflowStageShortSerializer(
        read_only=True,
        label=_("Этап-источник"),
        help_text=_("Показывается развёрнуто, для записи см. write-сериализатор"),
    )
    to_stage = WorkflowStageShortSerializer(
        read_only=True,
        label=_("Этап-цель"),
        help_text=_("Показывается развёрнуто, для записи см. write-сериализатор"),
    )

    class Meta:
        model = StageTransition
        fields = (
            "id",
            "is_active",
            "from_stage",
            "to_stage",
            "created_at",
            "updated_at",
        )


class WriteStageTransitionSerializer(serializers.ModelSerializer):
    """Связь между этапами — валидация входных данных (create/update)."""

    class Meta:
        model = StageTransition
        fields = (
            "id",
            "is_active",
            "from_stage",
            "to_stage",
        )

    def validate(self, attrs: dict) -> dict:
        """
        Проверка самосвязи, правил модели и циклов в графе этапов.

        Правила модели (один workflow, допустимые типы этапов) проверяет `clean()`. Цикл ищется только
        среди активных связей: неактивная связь в графе не участвует и цикла образовать не может.
        При PATCH недостающие значения берутся из сохранённой связи.
        """
        from_stage = attrs.get("from_stage", getattr(self.instance, "from_stage", None))
        to_stage = attrs.get("to_stage", getattr(self.instance, "to_stage", None))
        is_active = attrs.get("is_active", getattr(self.instance, "is_active", True))
        if from_stage.pk == to_stage.pk:
            raise serializers.ValidationError(
                {"to_stage": _("Этап не может вести сам на себя.")},
            )
        validate_model_clean(model=StageTransition, attrs=attrs, instance=self.instance)
        if is_active and stage_transition_service.creates_cycle(
            from_stage=from_stage,
            to_stage=to_stage,
            exclude_pk=getattr(self.instance, "pk", None),
        ):
            raise serializers.ValidationError(
                {"to_stage": _("Связь образует цикл.")},
            )
        return attrs
