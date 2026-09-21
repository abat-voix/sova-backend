from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.core.api.serializers import UserShortSerializer
from sova.processes.models import ActionResult
from sova.workflows.api.serializers import ActionOutcomeShortSerializer


class ActionResultSerializer(serializers.ModelSerializer):
    """Результат действия — представление для чтения (list/retrieve)."""

    outcome = ActionOutcomeShortSerializer(
        read_only=True,
        label=_("Исход"),
        help_text=_("Показывается развёрнуто, для записи см. write-сериализатор"),
    )
    created_by = UserShortSerializer(
        read_only=True,
        label=_("Создал"),
        help_text=_("Пользователь, зафиксировавший результат; пусто, если он удалён"),
    )

    class Meta:
        model = ActionResult
        fields = (
            "id",
            "action_instance",
            "outcome",
            "outcome_name_snapshot",
            "comment",
            "created_at",
            "created_by",
        )
