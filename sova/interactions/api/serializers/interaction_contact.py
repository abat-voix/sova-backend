from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.interactions.models import InteractionContact


class ContactPersonCompactSerializer(serializers.Serializer):
    """Контакт в составе взаимодействия без повторной вложенной модели контрагента."""

    id = serializers.UUIDField(read_only=True)
    full_name = serializers.CharField(read_only=True)
    position = serializers.CharField(read_only=True)
    email = serializers.EmailField(read_only=True)
    phone = serializers.CharField(read_only=True)


class InteractionContactSerializer(serializers.ModelSerializer):
    contact_person = ContactPersonCompactSerializer(read_only=True)

    class Meta:
        model = InteractionContact
        fields = ("id", "contact_person", "linked_at")


class LinkContactPersonSerializer(serializers.Serializer):
    contact_person = serializers.UUIDField(
        label=_("Контактное лицо"),
        help_text=_("UUID контактного лица из каталога"),
    )
