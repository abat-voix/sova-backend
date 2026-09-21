from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from sova.core.api.serializers import UserShortSerializer
from sova.interactions.api.serializers import InteractionShortSerializer
from sova.processes.api.serializers.board import BoardOutcomeSerializer
from sova.processes.enum import ActionInstanceStatus
from sova.processes.models import ActionInstance, ActionResult
from sova.workflows.api.serializers import WorkflowActionShortSerializer


class ActionResultShortSerializer(serializers.ModelSerializer):
    """Результат выполненного действия — теми же полями, что и `BoardResult` на доске процесса."""

    outcome_name = serializers.CharField(
        source="outcome_name_snapshot",
        label=_("Исход"),
        help_text=_("Название исхода на момент выполнения"),
    )
    created_by = UserShortSerializer(
        read_only=True,
        label=_("Автор"),
        help_text=_("Кто завершил действие; пусто, если пользователь удалён"),
    )

    class Meta:
        model = ActionResult
        fields = ("outcome_name", "comment", "created_at", "created_by")


class ActionInstanceSerializer(serializers.ModelSerializer):
    """
    Экземпляр действия — представление для чтения (list/retrieve).

    Состав полей повторяет карточку действия на доске процесса (`BoardAction`), чтобы список действий
    можно было показывать теми же карточками, но по всем процессам сразу.
    """

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
    interaction = InteractionShortSerializer(
        source="stage_instance.workflow_instance.interaction",
        read_only=True,
        label=_("Взаимодействие"),
        help_text=_("Вуз или клиент, с которым ведётся работа"),
    )
    workflow_instance = serializers.UUIDField(
        source="stage_instance.workflow_instance_id",
        read_only=True,
        label=_("Процесс"),
        help_text=_("Процесс workflow, которому принадлежит действие"),
    )
    stage_name_snapshot = serializers.CharField(
        source="stage_instance.stage.name",
        read_only=True,
        label=_("Название этапа"),
        help_text=_("Текущее название этапа в определении workflow: слепка названия у этапа нет"),
    )
    is_optional = serializers.BooleanField(
        source="action.is_optional",
        read_only=True,
        label=_("Необязательное"),
        help_text=_("Необязательное действие не мешает закрыть этап и остаётся доступным после его закрытия"),
    )
    is_trigger_only = serializers.BooleanField(
        source="action.is_trigger_only",
        read_only=True,
        label=_("Только по переходу"),
        help_text=_("Действие запускается переходом по исходу другого действия, а не вместе с этапом"),
    )
    is_triggered = serializers.SerializerMethodField(
        label=_("Запущено переходом"),
        help_text=_("Для действия «только по переходу»: запущено ли оно; иначе оно ждёт запуска"),
    )
    is_overdue = serializers.SerializerMethodField(
        label=_("Просрочено"),
        help_text=_("Невыполненное действие, плановое окончание которого прошло"),
    )
    attachments_count = serializers.IntegerField(
        read_only=True,
        label=_("Вложений"),
        help_text=_("Число файлов, приложенных к исполнению"),
    )
    result = ActionResultShortSerializer(
        read_only=True,
        label=_("Результат"),
        help_text=_("Пусто, пока действие не выполнено"),
    )
    available_outcomes = serializers.SerializerMethodField(
        label=_("Доступные исходы"),
        help_text=_("Активные исходы действия; пусто, если действие не в работе"),
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
            "is_optional",
            "is_trigger_only",
            "is_triggered",
            "is_overdue",
            "attachments_count",
            "stage_instance",
            "stage_name_snapshot",
            "workflow_instance",
            "interaction",
            "action",
            "responsible",
            "result",
            "available_outcomes",
        )

    def get_is_triggered(self, instance: ActionInstance) -> bool:
        """Запущено ли действие переходом по исходу другого действия."""
        return instance.triggered_at is not None

    def get_is_overdue(self, instance: ActionInstance) -> bool:
        """Просрочено ли действие: не выполнено, а плановое окончание уже прошло."""
        return (
            instance.status != ActionInstanceStatus.COMPLETED
            and instance.planned_end is not None
            and instance.planned_end < timezone.now()
        )

    @extend_schema_field(BoardOutcomeSerializer(many=True))
    def get_available_outcomes(self, instance: ActionInstance) -> list[dict]:
        """Исходы, которые можно выбрать при завершении: только у действия в работе."""
        if instance.status != ActionInstanceStatus.IN_PROGRESS:
            return []

        # Выборка вьюсета кладёт активные исходы в active_outcomes; вне её берём их запросом
        outcomes = getattr(instance.action, "active_outcomes", None)
        if outcomes is None:
            outcomes = instance.action.action_outcomes.filter(is_active=True).order_by("code")
        return BoardOutcomeSerializer(outcomes, many=True).data
