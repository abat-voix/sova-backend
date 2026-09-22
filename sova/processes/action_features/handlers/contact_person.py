from rest_framework import serializers

from sova.catalog.api.serializers import WriteContactPersonSerializer
from sova.catalog.models import ContactPerson
from sova.processes.action_features.base import ActionFeatureResult
from sova.processes.action_features.errors import ActionFeatureError


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
        return ActionFeatureResult("contact_person", contact.pk, {"full_name": contact.full_name})


class SelectContactPersonHandler:
    code = "contact_person.select"

    def execute(self, *, context, data: dict, settings: dict) -> ActionFeatureResult:
        contact_id = data.get("contact_person")
        query = ContactPerson.objects.filter(pk=contact_id)
        if context.university:
            query = query.filter(university=context.university)
        elif context.b2c_client:
            query = query.filter(b2c_client=context.b2c_client)
        else:
            raise ActionFeatureError("invalid_action_context")
        contact = query.first()
        if contact is None:
            raise ActionFeatureError("target_outside_interaction", "Контакт не принадлежит контрагенту взаимодействия.", 400)
        return ActionFeatureResult("contact_person", contact.pk, {"full_name": contact.full_name})
