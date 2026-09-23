from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.workflows.api.serializers.workflow_action import WorkflowActionShortSerializer
from sova.workflows.models import ActionFeature


class ActionFeatureSerializer(serializers.ModelSerializer):
    """Настроенная возможность действия — представление для чтения."""

    action = WorkflowActionShortSerializer(
        read_only=True,
        label=_("Действие"),
        help_text=_("Показывается развёрнуто, для записи см. write-сериализатор"),
    )

    class Meta:
        model = ActionFeature
        fields = (
            "id",
            "code",
            "sort_order",
            "is_active",
            "settings",
            "action",
            "created_at",
            "updated_at",
        )


class WriteActionFeatureSerializer(serializers.ModelSerializer):
    """Настроенная возможность действия — данные создания и изменения."""

    class Meta:
        model = ActionFeature
        fields = (
            "id",
            "code",
            "sort_order",
            "is_active",
            "settings",
            "action",
        )

    def validate_settings(self, value: object) -> dict:
        """Admin допускает JSON, но runtime ожидает объект с настройками."""
        if not isinstance(value, dict):
            raise serializers.ValidationError(_("Настройки должны быть JSON-объектом."))
        return value
