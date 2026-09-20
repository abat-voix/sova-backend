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


class WriteActionResultSerializer(serializers.ModelSerializer):
    """Результат действия — валидация входных данных (фиксация результата)."""

    class Meta:
        model = ActionResult
        fields = (
            "id",
            "action_instance",
            "outcome",
            "comment",
        )

    def validate(self, attrs: dict) -> dict:
        """
        Проверка исхода по правилам действия.

        Исход должен быть активным и принадлежать действию экземпляра. Если он
        требует комментарий (`comment_required`) или вложение (`attachment_required`),
        они должны быть заданы: комментарий — в запросе, вложение — загружено к
        экземпляру действия заранее.
        """
        action_instance = attrs["action_instance"]
        outcome = attrs["outcome"]

        if outcome.action_id != action_instance.action_id:
            raise serializers.ValidationError(
                {"outcome": _("Исход относится к другому действию.")},
            )
        if not outcome.active:
            raise serializers.ValidationError(
                {"outcome": _("Исход неактивен.")},
            )
        if outcome.comment_required and not attrs.get("comment", "").strip():
            raise serializers.ValidationError(
                {"comment": _("Для этого исхода комментарий обязателен.")},
            )
        if (
            outcome.attachment_required
            and not action_instance.action_attachments.exists()
        ):
            raise serializers.ValidationError(
                {"outcome": _("Для этого исхода сначала нужно загрузить вложение.")},
            )
        return attrs

    def create(self, validated_data: dict) -> ActionResult:
        """Создаёт результат, фиксируя слепок названия исхода."""
        validated_data["outcome_name_snapshot"] = validated_data["outcome"].name
        return super().create(validated_data)
