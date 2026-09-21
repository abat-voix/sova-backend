from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.processes.api.serializers.action_instance import ActionInstanceSerializer
from sova.processes.api.serializers.action_result import ActionResultSerializer
from sova.processes.api.serializers.stage_instance import StageInstanceSerializer
from sova.processes.api.serializers.stage_rollback import StageRollbackSerializer
from sova.processes.enum import RollbackMode
from sova.processes.models import StageInstance
from sova.workflows.models import ActionOutcome


class CompleteActionSerializer(serializers.Serializer):
    """Завершение действия — валидация входных данных."""

    outcome = serializers.PrimaryKeyRelatedField(
        queryset=ActionOutcome.objects.all(),
        label=_("Исход"),
        help_text=_("Передаётся id исхода этого действия; правила комментария и вложения задаёт сам исход"),
    )
    comment = serializers.CharField(
        default="",
        required=False,
        allow_blank=True,
        label=_("Комментарий"),
        help_text=_("Обязателен, если этого требует выбранный исход"),
    )


class CompleteActionResultSerializer(serializers.Serializer):
    """Завершение действия — что изменилось в процессе, чтобы интерфейс обновил доску без перезагрузки."""

    action_instance = ActionInstanceSerializer(
        read_only=True,
        label=_("Действие"),
        help_text=_("Завершённое исполнение действия"),
    )
    result = ActionResultSerializer(
        read_only=True,
        label=_("Результат"),
        help_text=_("Зафиксированный результат со слепком названия исхода"),
    )
    activated_actions = ActionInstanceSerializer(
        many=True,
        read_only=True,
        label=_("Запущенные действия"),
        help_text=_("Действия, которые стали доступны после завершения этого"),
    )
    opened_stages = StageInstanceSerializer(
        many=True,
        read_only=True,
        label=_("Открытые этапы"),
        help_text=_("Этапы, которые открылись, включая созданные для новых программ и продуктов"),
    )
    completed_stages = StageInstanceSerializer(
        many=True,
        read_only=True,
        label=_("Закрытые этапы"),
        help_text=_("Этапы, закрытые этим действием или сразу при открытии"),
    )
    is_workflow_completed = serializers.BooleanField(
        read_only=True,
        label=_("Процесс завершён"),
        help_text=_("Истина, если закрыты все этапы"),
    )


class CancelStageSerializer(serializers.Serializer):
    """Отмена этапа — валидация входных данных."""

    mode = serializers.ChoiceField(
        choices=RollbackMode.choices,
        label=_("Режим"),
        help_text=_("Как вернуть этап возврата: заново целиком или только последнее обязательное действие"),
    )
    reason = serializers.CharField(
        label=_("Причина"),
        help_text=_("Записывается в журнал откатов"),
    )
    return_to = serializers.PrimaryKeyRelatedField(
        queryset=StageInstance.objects.all(),
        required=False,
        allow_null=True,
        label=_("Этап возврата"),
        help_text=_("Нужен, если у отменяемого этапа несколько предшественников; варианты отдаёт доска"),
    )


class CancelStageResultSerializer(serializers.Serializer):
    """Отмена этапа — что изменилось в процессе."""

    rollback = StageRollbackSerializer(
        read_only=True,
        label=_("Откат"),
        help_text=_("Запись журнала об этом откате"),
    )
    returned_stage = StageInstanceSerializer(
        read_only=True,
        label=_("Этап возврата"),
        help_text=_("Этап, на который вернулся процесс"),
    )
    reset_stages = StageInstanceSerializer(
        many=True,
        read_only=True,
        label=_("Сброшенные этапы"),
        help_text=_("Этапы после этапа возврата, которые снова ожидают и будут выполнены заново"),
    )
