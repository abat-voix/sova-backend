from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.core.api.serializers import UserShortSerializer
from sova.core.api.validators import validate_model_clean
from sova.interactions.api.serializers.contract import ContractShortSerializer
from sova.interactions.api.serializers.interaction_product import (
    InteractionProductShortSerializer,
)
from sova.interactions.models import License
from sova.interactions.services import visible_contracts


class LicenseSerializer(serializers.ModelSerializer):
    """Лицензия — представление для чтения (list/retrieve)."""

    contract = ContractShortSerializer(
        read_only=True,
        label=_("Договор"),
        help_text=_("Показывается развёрнуто, для записи см. write-сериализатор"),
    )
    interaction_product = InteractionProductShortSerializer(
        read_only=True,
        label=_("Продукт взаимодействия"),
        help_text=_("Показывается развёрнуто, для записи см. write-сериализатор"),
    )
    created_by = UserShortSerializer(
        read_only=True,
        label=_("Создал"),
        help_text=_("Пользователь, оформивший лицензию; пусто, если он удалён"),
    )

    class Meta:
        model = License
        fields = (
            "id",
            "created_at",
            "signed_at",
            "superseded_at",
            "valid_until_year",
            "is_signed",
            "is_active",
            "contract",
            "interaction_product",
            "created_by",
        )


class WriteLicenseSerializer(serializers.ModelSerializer):
    """
    Лицензия — валидация входных данных (create/update).

    `is_active`, `superseded_at` и автор не принимаются: ими управляет
    LicenseService при перезаключении.
    """

    class Meta:
        model = License
        fields = (
            "id",
            "signed_at",
            "valid_until_year",
            "is_signed",
            "contract",
            "interaction_product",
        )

    def validate_contract(self, contract):
        """Договор лицензии должен быть видим пользователю запроса."""
        request = self.context["request"]
        if not visible_contracts(request.user).filter(pk=contract.pk).exists():
            raise serializers.ValidationError(_("Договор не найден."), code="not_found")
        return contract

    def validate(self, attrs: dict) -> dict:
        """Проверка принадлежности одному взаимодействию и неизменности истории."""
        if self.instance is None:
            validate_model_clean(model=License, attrs=attrs)
            return attrs

        if not self.instance.is_active:
            raise serializers.ValidationError(
                _("Заменённая лицензия — запись истории, её нельзя изменять."),
            )
        for field_name in ("contract", "interaction_product"):
            if field_name in attrs and attrs[field_name] != getattr(self.instance, field_name):
                raise serializers.ValidationError(
                    {field_name: _("Изменить нельзя: для новой пары создайте новую лицензию.")},
                )
        return attrs
