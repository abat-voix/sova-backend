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
            "triggered_at",
            "execution_no",
            "stage_instance",
            "action",
            "responsible",
        )
