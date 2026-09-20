from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.workflows.api.serializers.workflow_action import WorkflowActionShortSerializer
from sova.workflows.models import ActionDependency
from sova.workflows.services import action_dependency_service


class ActionDependencySerializer(serializers.ModelSerializer):
    """Зависимость действия — представление для чтения (list/retrieve)."""

    action = WorkflowActionShortSerializer(
        read_only=True,
        label=_("Действие"),
        help_text=_("Показывается развёрнуто, для записи см. write-сериализатор"),
    )
    depends_on_action = WorkflowActionShortSerializer(
        read_only=True,
        label=_("Зависит от действия"),
        help_text=_("Показывается развёрнуто, для записи см. write-сериализатор"),
    )

    class Meta:
        model = ActionDependency
        fields = (
            "id",
            "active",
            "action",
            "depends_on_action",
            "created_at",
            "updated_at",
        )


class WriteActionDependencySerializer(serializers.ModelSerializer):
    """Зависимость действия — валидация входных данных (create/update)."""

    class Meta:
        model = ActionDependency
        fields = (
            "id",
            "active",
            "action",
            "depends_on_action",
        )

    def validate(self, attrs: dict) -> dict:
        """Проверка одного workflow, отсутствия самозависимости и циклов в графе."""
        action = attrs.get("action", getattr(self.instance, "action", None))
        depends_on_action = attrs.get(
            "depends_on_action",
            getattr(self.instance, "depends_on_action", None),
        )
        is_active = attrs.get("active", getattr(self.instance, "active", True))

        if action.pk == depends_on_action.pk:
            raise serializers.ValidationError(
                {"depends_on_action": _("Действие не может зависеть от самого себя.")},
            )
        if action.stage.workflow_id != depends_on_action.stage.workflow_id:
            raise serializers.ValidationError(
                {"depends_on_action": _("Действие относится к другому workflow.")},
            )
        # Неактивная зависимость в графе не участвует, цикла образовать не может
        if is_active and action_dependency_service.creates_cycle(
            action=action,
            depends_on_action=depends_on_action,
            exclude_pk=getattr(self.instance, "pk", None),
        ):
            raise serializers.ValidationError(
                {"depends_on_action": _("Зависимость образует цикл.")},
            )
        return attrs
