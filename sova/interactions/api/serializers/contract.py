from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.interactions.api.serializers.interaction import InteractionShortSerializer
from sova.interactions.models import Contract


class ContractShortSerializer(serializers.ModelSerializer):
    """Договор — краткое представление для вложенного использования."""

    class Meta:
        model = Contract
        fields = ("id", "contract_number")


class ContractSerializer(serializers.ModelSerializer):
    """Договор — представление для чтения (list/retrieve)."""

    interaction = InteractionShortSerializer(
        read_only=True,
        label=_("Взаимодействие"),
        help_text=_("Показывается развёрнуто, для записи см. write-сериализатор"),
    )

    class Meta:
        model = Contract
        fields = (
            "id",
            "file",
            "contract_number",
            "sent_at",
            "corrected_at",
            "signed_at",
            "interaction",
            "created_at",
            "updated_at",
        )


class WriteContractSerializer(serializers.ModelSerializer):
    """Договор — валидация входных данных (create/update)."""

    class Meta:
        model = Contract
        fields = (
            "id",
            "file",
            "contract_number",
            "sent_at",
            "corrected_at",
            "signed_at",
            "interaction",
        )
        # В модели interaction nullable ради headless-договоров импорта реестра; через API
        # договор всегда создаётся в рамках взаимодействия.
        extra_kwargs = {"interaction": {"required": True, "allow_null": False}}

    def validate(self, attrs: dict) -> dict:
        """Проверка порядка дат: отправка → корректировка → подписание."""
        # При PATCH недостающие даты берутся из сохранённого договора
        dates = [
            (name, attrs.get(name, getattr(self.instance, name, None)))
            for name in ("sent_at", "corrected_at", "signed_at")
        ]
        filled = [(name, value) for name, value in dates if value is not None]

        for (_previous_name, previous), (name, value) in zip(filled, filled[1:]):
            if value < previous:
                raise serializers.ValidationError(
                    {name: _("Дата не может быть раньше предыдущего шага договора.")},
                )
        return attrs

