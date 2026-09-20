from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.workflows.api.serializers.action_outcome import ActionOutcomeShortSerializer
from sova.workflows.api.serializers.workflow_action import WorkflowActionShortSerializer
from sova.workflows.models import ActionTransition


class ActionTransitionSerializer(serializers.ModelSerializer):
    """Переход действия — представление для чтения (list/retrieve)."""

    outcome = ActionOutcomeShortSerializer(
        read_only=True,
        label=_("Исход"),
        help_text=_("Показывается развёрнуто, для записи см. write-сериализатор"),
    )
    target_action = WorkflowActionShortSerializer(
        read_only=True,
        label=_("Целевое действие"),
        help_text=_("Показывается развёрнуто, для записи см. write-сериализатор"),
    )

    class Meta:
        model = ActionTransition
        fields = (
            "id",
            "active",
            "outcome",
            "target_action",
            "created_at",
            "updated_at",
        )


class WriteActionTransitionSerializer(serializers.ModelSerializer):
    """Переход действия — валидация входных данных (create/update)."""

    class Meta:
        model = ActionTransition
        fields = (
            "id",
            "active",
            "outcome",
            "target_action",
        )

    def validate(self, attrs: dict) -> dict:
        """
        Проверка, что исход и целевое действие принадлежат одному этапу.

        Переход на действие другого этапа означал бы ветвление по этапам, а порядок этапов
        задаётся только связями между этапами.
        """
        outcome = attrs.get("outcome", getattr(self.instance, "outcome", None))
        target_action = attrs.get(
            "target_action",
            getattr(self.instance, "target_action", None),
        )

        if outcome.action.stage_id != target_action.stage_id:
            raise serializers.ValidationError(
                {"target_action": _("Целевое действие относится к другому этапу.")},
            )
        return attrs
