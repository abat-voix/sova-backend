from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.catalog.services.contact_affiliation import contact_affiliation_service
from sova.interactions.models import InteractionContact


class ContactPersonCompactSerializer(serializers.Serializer):
    """Контакт в составе взаимодействия: должность — у контрагента этого взаимодействия."""

    id = serializers.UUIDField(read_only=True)
    full_name = serializers.CharField(read_only=True)
    position = serializers.CharField(read_only=True, help_text=_("Должность у контрагента взаимодействия"))
    email = serializers.EmailField(read_only=True)
    phone = serializers.CharField(read_only=True)
    telegram = serializers.CharField(read_only=True)


class InteractionContactSerializer(serializers.ModelSerializer):
    """
    Привязка контакта к взаимодействию.

    Должность берётся из аннотации `position` (`contact_affiliation_service.annotate_interaction_position`),
    без неё — отдельным запросом к связи.
    """

    contact_person = ContactPersonCompactSerializer(read_only=True)

    class Meta:
        model = InteractionContact
        fields = ("id", "contact_person", "linked_at")

    def to_representation(self, instance: InteractionContact) -> dict:
        data = super().to_representation(instance)
        position = getattr(instance, "position", None)
        if position is None:
            position = contact_affiliation_service.position_for(
                contact=instance.contact_person,
                organization=contact_affiliation_service.interaction_counterparty(interaction=instance.interaction),
            )
        data["contact_person"]["position"] = position
        return data


class LinkContactPersonSerializer(serializers.Serializer):
    contact_person = serializers.UUIDField(
        label=_("Контактное лицо"),
        help_text=_("UUID контактного лица из каталога"),
    )
