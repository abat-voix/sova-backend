from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.catalog.api.serializers.b2c_client import B2CClientShortSerializer
from sova.catalog.api.serializers.university import UniversityShortSerializer
from sova.catalog.models import ContactPerson
from sova.core.api.validators import validate_exactly_one_counterparty, validate_model_constraints


class ContactPersonSerializer(serializers.ModelSerializer):
    """Контактное лицо — представление для чтения (list/retrieve)."""

    university = UniversityShortSerializer(
        read_only=True,
        label=_("Вуз"),
        help_text=_("Показывается развёрнуто, для записи см. write-сериализатор"),
    )
    b2c_client = B2CClientShortSerializer(
        read_only=True,
        label=_("B2C-клиент"),
        help_text=_("Показывается развёрнуто, для записи см. write-сериализатор"),
    )

    class Meta:
        model = ContactPerson
        fields = (
            "id",
            "full_name",
            "position",
            "email",
            "phone",
            "is_active",
            "university",
            "b2c_client",
            "created_at",
            "updated_at",
        )


class WriteContactPersonSerializer(serializers.ModelSerializer):
    """Контактное лицо — валидация входных данных (create/update)."""

    class Meta:
        model = ContactPerson
        fields = (
            "id",
            "full_name",
            "position",
            "email",
            "phone",
            "is_active",
            "university",
            "b2c_client",
        )

    def validate(self, attrs: dict) -> dict:
        """Проверка, что задан ровно один контрагент, и уникальности ФИО у него без учёта регистра."""
        validate_exactly_one_counterparty(attrs=attrs, instance=self.instance)
        validate_model_constraints(model=ContactPerson, attrs=attrs, instance=self.instance)
        return attrs
