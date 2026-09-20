from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.core.api.serializers import UserShortSerializer
from sova.core.api.validators import validate_model_clean
from sova.processes.models import StageInstance
from sova.workflows.api.serializers import WorkflowStageShortSerializer


class StageInstanceSerializer(serializers.ModelSerializer):
    """Экземпляр этапа — представление для чтения (list/retrieve)."""

    stage = WorkflowStageShortSerializer(
        read_only=True,
        label=_("Этап"),
        help_text=_("Показывается развёрнуто, для записи см. write-сериализатор"),
    )
    added_by = UserShortSerializer(
        read_only=True,
        label=_("Кто добавил"),
        help_text=_("Пользователь, добавивший этап; пусто, если он удалён"),
    )

    class Meta:
        model = StageInstance
        fields = (
            "id",
            "context_type",
            "context_id",
            "status",
            "added_at",
            "completed_at",
            "workflow_instance",
            "stage",
            "added_by",
        )


class WriteStageInstanceSerializer(serializers.ModelSerializer):
    """Экземпляр этапа — валидация входных данных (create)."""

    class Meta:
        model = StageInstance
        fields = (
            "id",
            "context_type",
            "context_id",
            "status",
            "workflow_instance",
            "stage",
        )

    def validate(self, attrs: dict) -> dict:
        """
        Проверка этапа и контекста.

        Этап должен принадлежать workflow процесса. Полиморфный `context_id`
        (взаимодействие / направление / программа / продукт) проверяет
        `StageInstance.clean()`: запись существует и относится к взаимодействию процесса.
        """
        if attrs["stage"].workflow_id != attrs["workflow_instance"].workflow_id:
            raise serializers.ValidationError(
                {"stage": _("Этап относится к другому workflow, чем процесс.")},
            )
        validate_model_clean(model=StageInstance, attrs=attrs)
        return attrs
