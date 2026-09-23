from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from drf_spectacular.utils import extend_schema_field

from sova.core.api.serializers import UserShortSerializer
from sova.interactions.api.serializers.interaction import InteractionShortSerializer
from sova.interactions.models import Contract
from sova.interactions.services import responsible_service


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
    suggested_manager = serializers.SerializerMethodField(
        label=_("Предлагаемый ответственный"),
        help_text=_(
            "Пользователь, найденный по ФИО менеджера из реестра (draft_manager_full_name), — подсказка для "
            "выбора ответственного при создании взаимодействия; null — договор уже привязан, ФИО пусто, "
            "пользователь не найден или найдено несколько"
        ),
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
            "draft_manager_full_name",
            "suggested_manager",
            "created_at",
            "updated_at",
        )

    @extend_schema_field(UserShortSerializer(allow_null=True))
    def get_suggested_manager(self, instance: Contract) -> dict | None:
        """Подсказка только для договора без взаимодействия; активные пользователи выбираются один раз на ответ."""
        if instance.interaction_id is not None or not instance.draft_manager_full_name:
            return None
        if "active_users" not in self.context:
            self.context["active_users"] = list(get_user_model().objects.filter(is_active=True))
        manager = responsible_service.suggest_manager(
            full_name=instance.draft_manager_full_name, users=self.context["active_users"]
        )
        return UserShortSerializer(manager).data if manager is not None else None


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



class AttachToNewInteractionSerializer(serializers.Serializer):
    """Создание взаимодействия из договора — ответственный, если его нужно указать явно."""

    manager = serializers.PrimaryKeyRelatedField(
        queryset=get_user_model().objects.filter(is_active=True),
        required=False,
        allow_null=True,
        label=_("Ответственный менеджер"),
        help_text=_(
            "Id активного пользователя — ответственный нового взаимодействия. Не указан — взаимодействие "
            "создаётся без ответственного; подсказка — suggested_manager договора"
        ),
    )
