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
            "is_active",
            "is_comment_required",
            "is_attachment_required",
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
            "is_active",
            "is_comment_required",
            "is_attachment_required",
            "action",
        )

    def validate(self, attrs: dict) -> dict:
        """
        Проверка, что исход с активным переходом остаётся в этапе своей цели.

        Иначе переход вышел бы за границы этапа: ветвление по этапам запрещено.
        """
        if self.instance is None:
            return attrs
        action = attrs.get("action", self.instance.action)
        # RelatedObjectDoesNotExist наследует AttributeError: у исхода может не быть перехода
        transition = getattr(self.instance, "transition", None)
        if transition is not None and transition.is_active and transition.target_action.stage_id != action.stage_id:
            raise serializers.ValidationError(
                {"action": _("Исход ведёт на действие другого этапа — действие должно быть из того же этапа.")},
            )
        return attrs
