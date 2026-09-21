from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.core.api.serializers import UserShortSerializer
from sova.workflows.models import Workflow


class WorkflowShortSerializer(serializers.ModelSerializer):
    """Workflow — краткое представление для вложенного использования."""

    class Meta:
        model = Workflow
        fields = ("id", "name", "code")


class WorkflowSerializer(serializers.ModelSerializer):
    """Workflow — представление для чтения (list/retrieve)."""

    created_by = UserShortSerializer(
        read_only=True,
        label=_("Создал"),
        help_text=_("Автор шаблона; пусто, если пользователь удалён"),
    )
    stages_count = serializers.IntegerField(
        read_only=True,
        label=_("Количество этапов"),
        help_text=_("Считается через annotate() на стороне ViewSet"),
    )

    class Meta:
        model = Workflow
        fields = (
            "id",
            "name",
            "code",
            "audience",
            "description",
            "stale_threshold_days",
            "is_base",
            "is_active",
            "created_by",
            "created_at",
            "updated_at",
            "stages_count",
        )


class WriteWorkflowSerializer(serializers.ModelSerializer):
    """Workflow — валидация входных данных (create/update)."""

    class Meta:
        model = Workflow
        fields = (
            "id",
            "name",
            "code",
            "audience",
            "description",
            "stale_threshold_days",
            "is_base",
            "is_active",
        )

    def validate(self, attrs: dict) -> dict:
        """
        Проверка «один базовый workflow на аудиторию».

        Условное ограничение БД `one_base_workflow_per_audience` DRF не проверяет,
        а без валидации клиент получил бы ошибку БД. Недостающие значения берутся
        из сохранённого workflow (PATCH) или из default поля модели (создание):
        DRF не подставляет model default в `attrs`, а аудитория по умолчанию — B2B.
        """
        audience_field = Workflow._meta.get_field("audience")
        is_base = attrs.get("is_base", getattr(self.instance, "is_base", False))
        audience = attrs.get(
            "audience",
            getattr(self.instance, "audience", audience_field.get_default()),
        )
        if not is_base:
            return attrs

        conflicting = Workflow.objects.filter(is_base=True, audience=audience)
        if self.instance is not None:
            conflicting = conflicting.exclude(pk=self.instance.pk)
        if conflicting.exists():
            raise serializers.ValidationError(
                {"is_base": _("Для этой аудитории уже есть базовый workflow.")},
            )
        return attrs
