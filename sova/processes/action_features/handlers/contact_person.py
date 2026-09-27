from rest_framework import serializers

from sova.catalog.api.serializers import WriteContactPersonSerializer
from sova.catalog.models import ContactPerson
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


def _target_data(contact: ContactPerson, link=None) -> dict:
    data = {
        "full_name": contact.full_name,
        "position": contact.position,
        "email": contact.email,
        "phone": contact.phone,
    }
    if link is not None:
        data["linked_at"] = link.linked_at.isoformat()
    return data


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


class CreateContactPersonHandler:
    code = "contact_person.create"

    def execute(self, *, context, data: dict, settings: dict) -> ActionFeatureResult:
        if not context.university and not context.b2c_client:
            raise ActionFeatureError("invalid_action_context")
        payload = dict(data)
        payload.update(
            university=context.university.pk if context.university else None,
            b2c_client=context.b2c_client.pk if context.b2c_client else None,
        )
        serializer = WriteContactPersonSerializer(data=payload)
        if not serializer.is_valid():
            raise serializers.ValidationError(serializer.errors)
        contact = serializer.save()
        link, _ = _link(context, contact)
        return ActionFeatureResult("contact_person", contact.pk, _target_data(contact, link))


class SelectContactPersonHandler:
    code = "contact_person.select"

    def execute(self, *, context, data: dict, settings: dict) -> ActionFeatureResult:
        contact_id = _contact_id(data)
        try:
            contact = ContactPerson.objects.get(pk=contact_id)
        except ContactPerson.DoesNotExist as error:
            raise ActionFeatureError("contact_not_found", "Контактное лицо не найдено.", 404) from error
        link, _ = _link(context, contact)
        return ActionFeatureResult("contact_person", contact.pk, _target_data(contact, link))


class LinkContactPersonHandler(SelectContactPersonHandler):
    code = "contact_person.link"


class UpdateContactPersonHandler:
    code = "contact_person.update"

    def execute(self, *, context, data: dict, settings: dict) -> ActionFeatureResult:
        contact_id = _contact_id(data)
        try:
            contact = ContactPerson.objects.get(pk=contact_id)
        except ContactPerson.DoesNotExist as error:
            raise ActionFeatureError("contact_not_found", "Контактное лицо не найдено.", 404) from error

        # Из действия можно менять только контакт, который уже принадлежит этому
        # взаимодействию. Так нельзя изменить постороннюю карточку, зная её UUID.
        if not context.interaction.contact_links.filter(
            contact_person=contact,
            unlinked_at__isnull=True,
        ).exists():
            raise ActionFeatureError(
                "contact_not_linked",
                "Контактное лицо не привязано к этому взаимодействию.",
                400,
            )

        payload = {
            "full_name": data.get("full_name", contact.full_name),
            "position": data.get("position", contact.position),
            "email": data.get("email", contact.email),
            "phone": data.get("phone", contact.phone),
            # Контрагент не редактируется из feature: это отдельная операция
            # каталога с собственными ограничениями для привязанных контактов.
            "university": contact.university_id,
            "b2c_client": contact.b2c_client_id,
            "is_active": contact.is_active,
        }
        serializer = WriteContactPersonSerializer(instance=contact, data=payload)
        if not serializer.is_valid():
            raise serializers.ValidationError(serializer.errors)
        contact = serializer.save()
        return ActionFeatureResult("contact_person", contact.pk, _target_data(contact))


class DeactivateContactPersonHandler:
    code = "contact_person.deactivate"

    def execute(self, *, context, data: dict, settings: dict) -> ActionFeatureResult:
        contact_id = _contact_id(data)
        try:
            contact = ContactPerson.objects.get(pk=contact_id)
        except ContactPerson.DoesNotExist as error:
            raise ActionFeatureError("contact_not_found", "Контактное лицо не найдено.", 404) from error

        if not context.interaction.contact_links.filter(
            contact_person=contact,
            unlinked_at__isnull=True,
        ).exists():
            raise ActionFeatureError(
                "contact_not_linked",
                "Контактное лицо не привязано к этому взаимодействию.",
                400,
            )
        if not contact.is_active:
            raise ActionFeatureError(
                "contact_inactive",
                "Контактное лицо уже деактивировано.",
                409,
            )

        contact.is_active = False
        contact.save(update_fields=("is_active", "updated_at"))
        return ActionFeatureResult("contact_person", contact.pk, _target_data(contact))
