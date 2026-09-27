from django.db import transaction
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.catalog.api.serializers.b2c_client import B2CClientShortSerializer
from sova.catalog.api.serializers.university import UniversityShortSerializer
from sova.catalog.models import ContactPerson
from sova.core.api.exceptions import ConflictError
from sova.core.api.validators import validate_exactly_one_counterparty, validate_model_constraints
from sova.interactions.models import InteractionContact


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

        university = attrs.get("university", getattr(self.instance, "university", None))
        b2c_client = attrs.get("b2c_client", getattr(self.instance, "b2c_client", None))

        self._ensure_counterparty_can_change(
            instance=self.instance,
            university=university,
            b2c_client=b2c_client,
        )

        validate_model_constraints(model=ContactPerson, attrs=attrs, instance=self.instance)
        return attrs

    @staticmethod
    def _ensure_counterparty_can_change(instance, university, b2c_client) -> None:
        if instance is None or not InteractionContact.objects.filter(
            contact_person=instance,
            unlinked_at__isnull=True,
        ).exists():
            return
        current_counterparty = (instance.university_id, instance.b2c_client_id)
        new_counterparty = (
            getattr(university, "pk", university),
            getattr(b2c_client, "pk", b2c_client),
        )
        if current_counterparty != new_counterparty:
            raise ConflictError(
                detail=_(
                    "Нельзя изменить контрагента: контактное лицо уже привязано к взаимодействию.",
                ),
                code="contact_counterparty_locked",
            )

    @transaction.atomic
    def update(self, instance, validated_data):
        """Повторно проверяет блокировку под блокировкой строки контакта."""
        locked_instance = ContactPerson.objects.select_for_update().get(pk=instance.pk)
        self._ensure_counterparty_can_change(
            instance=locked_instance,
            university=validated_data.get("university", locked_instance.university),
            b2c_client=validated_data.get("b2c_client", locked_instance.b2c_client),
        )
        return super().update(locked_instance, validated_data)
