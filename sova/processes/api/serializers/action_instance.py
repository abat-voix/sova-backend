from datetime import timedelta

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.core.api.serializers import UserShortSerializer
from sova.processes.models import ActionInstance
from sova.workflows.api.serializers import WorkflowActionShortSerializer


class ActionInstanceSerializer(serializers.ModelSerializer):
    """Экземпляр действия — представление для чтения (list/retrieve)."""

    action = WorkflowActionShortSerializer(
        read_only=True,
        label=_("Действие"),
        help_text=_("Показывается развёрнуто, для записи см. write-сериализатор"),
    )
    responsible = UserShortSerializer(
        read_only=True,
        label=_("Ответственный"),
        help_text=_("Исполнитель действия; пусто, если не назначен"),
    )

    class Meta:
        model = ActionInstance
        fields = (
            "id",
            "action_name_snapshot",
            "status",
            "planned_start",
            "planned_end",
            "actual_start",
            "actual_end",
            "execution_no",
            "stage_instance",
            "action",
            "responsible",
        )


class WriteActionInstanceSerializer(serializers.ModelSerializer):
    """Экземпляр действия — валидация входных данных (create)."""

    class Meta:
        model = ActionInstance
        fields = (
            "id",
            "status",
            "planned_start",
            "planned_end",
            "actual_start",
            "actual_end",
            "execution_no",
            "stage_instance",
            "action",
            "responsible",
        )

    def validate(self, attrs: dict) -> dict:
        """
        Проверка принадлежности действия этапу и порядка плановых дат.

        Если задано плановое начало, а окончание нет — оно вычисляется как
        начало + `default_duration_days` действия (так это поле описано в модели
        WorkflowAction); без плановой длительности окончание остаётся пустым.
        """
        action = attrs["action"]
        if action.stage_id != attrs["stage_instance"].stage_id:
            raise serializers.ValidationError(
                {"action": _("Действие относится к другому этапу, чем экземпляр этапа.")},
            )

        planned_start = attrs.get("planned_start")
        planned_end = attrs.get("planned_end")
        if planned_start and planned_end and planned_end < planned_start:
            raise serializers.ValidationError(
                {"planned_end": _("Плановое окончание не может быть раньше планового начала.")},
            )
        if planned_start and planned_end is None and action.default_duration_days:
            attrs["planned_end"] = planned_start + timedelta(days=action.default_duration_days)
        return attrs

    def create(self, validated_data: dict) -> ActionInstance:
        """Создаёт экземпляр действия, фиксируя слепок названия действия."""
        validated_data["action_name_snapshot"] = validated_data["action"].name
        return super().create(validated_data)
