from django.db import transaction
from rest_framework import serializers

from sova.catalog.api.serializers import WriteContactPersonSerializer
from sova.catalog.models import ContactPerson
from sova.catalog.services.contact_affiliation import contact_affiliation_service
from sova.interactions.exceptions import ContactLinkError
from sova.interactions.services import contact_link_service
from sova.processes.action_features.base import ActionFeatureResult
from sova.processes.action_features.errors import ActionFeatureError


def _contact_id(data: dict):
    """Проверяет UUID входного контакта и переводит ошибку в контракт feature API."""
    value = data.get("contact_person")
    try:
        return serializers.UUIDField(required=True).run_validation(value)
    except serializers.ValidationError as error:
        raise ActionFeatureError(
            "invalid_contact_person",
            "Укажите корректный UUID контактного лица.",
            400,
        ) from error


def _target_data(contact: ContactPerson, link, context) -> dict:
    """Итог для шага: должность — у контрагента текущего взаимодействия."""
    return {
        "full_name": contact.full_name,
        "position": contact_affiliation_service.position_for(
            contact=contact,
            organization=context.university or context.b2c_client,
        ),
        "email": contact.email,
        "phone": contact.phone,
        "telegram": contact.telegram,
        "linked_at": link.linked_at.isoformat(),
    }


def _link(context, contact: ContactPerson):
    try:
        return contact_link_service.link(
            interaction=context.interaction,
            contact_person=contact,
            actor=context.user,
        )
    except ContactLinkError as error:
        raise ActionFeatureError(
            error.error_code,
            str(error.detail),
            error.status_code,
        ) from error


class CreateContactPersonPayloadSerializer(WriteContactPersonSerializer):
    """Новый человек и его должность у контрагента взаимодействия."""

    position = serializers.CharField(required=False, allow_blank=True, default="", max_length=255)

    class Meta(WriteContactPersonSerializer.Meta):
        fields = (*WriteContactPersonSerializer.Meta.fields, "position")


class CreateContactPersonHandler:
    """Создаёт человека со связью с контрагентом взаимодействия и сразу привязывает к взаимодействию — атомарно."""

    code = "contact_person.create"

    def execute(self, *, context, data: dict, settings: dict) -> ActionFeatureResult:
        counterparty = context.university or context.b2c_client
        if counterparty is None:
            raise ActionFeatureError("invalid_action_context")
        serializer = CreateContactPersonPayloadSerializer(data=data)
        if not serializer.is_valid():
            raise serializers.ValidationError(serializer.errors)
        payload = serializer.validated_data
        with transaction.atomic():
            affiliation = contact_affiliation_service.create_contact(
                organization=counterparty,
                full_name=payload["full_name"],
                email=payload.get("email", ""),
                phone=payload.get("phone", ""),
                telegram=payload.get("telegram", ""),
                position=payload["position"],
            )
            contact = affiliation.contact
            link, _ = _link(context, contact)
        return ActionFeatureResult("contact_person", contact.pk, _target_data(contact, link, context))


class SelectContactPersonHandler:
    code = "contact_person.select"

    def execute(self, *, context, data: dict, settings: dict) -> ActionFeatureResult:
        contact_id = _contact_id(data)
        try:
            contact = ContactPerson.objects.get(pk=contact_id)
        except ContactPerson.DoesNotExist as error:
            raise ActionFeatureError("contact_not_found", "Контактное лицо не найдено.", 404) from error
        link, _ = _link(context, contact)
        return ActionFeatureResult("contact_person", contact.pk, _target_data(contact, link, context))


class LinkContactPersonHandler(SelectContactPersonHandler):
    code = "contact_person.link"
