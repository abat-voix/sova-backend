from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.core.api.serializers import UserShortSerializer
from sova.interactions.api.serializers import InteractionShortSerializer
from sova.processes.models import WorkflowInstance
from sova.workflows.api.serializers import WorkflowShortSerializer


class WorkflowInstanceSerializer(serializers.ModelSerializer):
    """Процесс workflow — представление для чтения (list/retrieve)."""

    workflow = WorkflowShortSerializer(
        read_only=True,
        label=_("Workflow"),
        help_text=_("Показывается развёрнуто, для записи см. write-сериализатор"),
    )
    interaction = InteractionShortSerializer(
        read_only=True,
        label=_("Взаимодействие"),
        help_text=_("Показывается развёрнуто, для записи см. write-сериализатор"),
    )
    created_by = UserShortSerializer(
        read_only=True,
        label=_("Создал"),
        help_text=_("Пользователь, запустивший процесс; пусто, если он удалён"),
    )

    class Meta:
        model = WorkflowInstance
        fields = (
            "id",
            "status",
            "started_at",
            "completed_at",
            "workflow",
            "interaction",
            "created_by",
        )


class WriteWorkflowInstanceSerializer(serializers.ModelSerializer):
    """
    Процесс workflow — валидация входных данных (запуск процесса).

    Принимает только workflow и взаимодействие: статус, этапы и действия создаёт движок, а его правила
    (активность workflow, аудитория, повторный запуск) проверяются при запуске.
    """

    class Meta:
        model = WorkflowInstance
        fields = (
            "id",
            "workflow",
            "interaction",
        )
        # Уникальность пары «workflow + взаимодействие» проверяет движок и отвечает 409 already_started
        validators = []
