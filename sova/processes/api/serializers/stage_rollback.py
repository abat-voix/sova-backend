from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.core.api.serializers import UserShortSerializer
from sova.processes.api.serializers.stage_instance import StageInstanceShortSerializer
from sova.processes.models import StageRollback


class StageRollbackSerializer(serializers.ModelSerializer):
    """Откат этапа — представление для чтения (list/retrieve)."""

    from_stage_instance = StageInstanceShortSerializer(
        read_only=True,
        label=_("Отменённый этап"),
        help_text=_("Показывается развёрнуто; этап, который пользователь отменил"),
    )
    to_stage_instance = StageInstanceShortSerializer(
        read_only=True,
        label=_("Этап возврата"),
        help_text=_("Показывается развёрнуто; этап, на который вернулся процесс"),
    )
    created_by = UserShortSerializer(
        read_only=True,
        label=_("Создал"),
        help_text=_("Пользователь, выполнивший откат; пусто, если он удалён"),
    )

    class Meta:
        model = StageRollback
        fields = (
            "id",
            "reason",
            "mode",
            "created_at",
            "workflow_instance",
            "from_stage_instance",
            "to_stage_instance",
            "created_by",
        )
