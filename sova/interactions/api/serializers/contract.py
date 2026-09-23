from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.core.files import validate_file_size
from sova.interactions.api.serializers.interaction import InteractionShortSerializer
from sova.interactions.models import Contract
from sova.interactions.services import visible_interactions


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
    files_count = serializers.IntegerField(
        source="files.count",
        read_only=True,
        label=_("Число загруженных файлов"),
        help_text=_("Включая прежние версии — см. /api/interactions/contract-files/"),
    )
    download_url = serializers.SerializerMethodField(
        label=_("Ссылка на скачивание текущего файла"),
        help_text=_("Пусто, если файл не загружен"),
    )

    class Meta:
        model = Contract
        fields = (
            "id",
            "file_name",
            "download_url",
            "contract_number",
            "sent_at",
            "corrected_at",
            "signed_at",
            "interaction",
            "files_count",
            "created_at",
            "updated_at",
        )

    def get_download_url(self, obj: Contract) -> str | None:
        if not obj.file:
            return None
        return reverse("interactions:contract-download", args=[obj.pk])


class WriteContractSerializer(serializers.ModelSerializer):
    """Договор — валидация входных данных (create/update)."""

    file = serializers.FileField(
        validators=[validate_file_size],
        required=False,
        allow_null=True,
        label=_("Файл договора"),
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
        )

    def validate_interaction(self, interaction):
        """Договор можно создать только для видимого пользователю взаимодействия."""
        request = self.context["request"]
        if not visible_interactions(request.user).filter(pk=interaction.pk).exists():
            raise serializers.ValidationError(_("Взаимодействие не найдено."), code="not_found")
        return interaction

    def _set_file_name(self, validated_data: dict) -> dict:
        """Исходное имя загруженного файла: ключ `file.name` в хранилище — случайный UUID."""
        uploaded_file = validated_data.get("file")
        if uploaded_file is not None:
            validated_data["file_name"] = uploaded_file.name
        return validated_data

    def create(self, validated_data: dict) -> Contract:
        return super().create(self._set_file_name(validated_data))

    def update(self, instance: Contract, validated_data: dict) -> Contract:
        return super().update(instance, self._set_file_name(validated_data))

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
