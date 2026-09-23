from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.core.api.serializers import UserShortSerializer
from sova.processes.api.serializers.action_instance import ActionInstanceSerializer
from sova.processes.models import ActionRollback


class ActionRollbackSerializer(serializers.ModelSerializer):
    """Откат действия — представление для чтения (list/retrieve)."""

    from_action_instance = ActionInstanceSerializer(
        read_only=True,
        label=_("Отменённое исполнение"),
        help_text=_("Показывается развёрнуто; исполнение, которое пользователь отменил"),
    )
    to_action_instance = ActionInstanceSerializer(
        read_only=True,
        label=_("Новое исполнение"),
        help_text=_("Показывается развёрнуто; исполнение, созданное откатом"),
    )
    created_by = UserShortSerializer(
        read_only=True,
        label=_("Создал"),
        help_text=_("Пользователь, выполнивший откат; пусто, если он удалён"),
    )

    class Meta:
        model = ActionRollback
        fields = (
            "id",
            "reason",
            "created_at",
            "workflow_instance",
            "stage_instance",
            "from_action_instance",
            "to_action_instance",
            "created_by",
        )
