from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.core.api.serializers import UserShortSerializer
from sova.interactions.api.serializers import InteractionShortSerializer
from sova.processes.models import WorkflowInstance
from sova.workflows.api.serializers import WorkflowShortSerializer
from sova.workflows.enum import Audience


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
    """Процесс workflow — валидация входных данных (запуск процесса)."""

    class Meta:
        model = WorkflowInstance
        fields = (
            "id",
            "status",
            "workflow",
            "interaction",
        )

    def validate(self, attrs: dict) -> dict:
        """Проверка, что шаблон активен и его аудитория соответствует контрагенту."""
        workflow = attrs["workflow"]
        interaction = attrs["interaction"]

        if not workflow.active:
            raise serializers.ValidationError(
                {"workflow": _("Неактивный workflow нельзя запустить.")},
            )
        expected_audience = (
            Audience.B2B if interaction.university_id else Audience.B2C
        )
        if workflow.audience != expected_audience:
            raise serializers.ValidationError(
                {
                    "workflow": _(
                        "Аудитория workflow не соответствует контрагенту взаимодействия.",
                    ),
                },
            )
        return attrs
