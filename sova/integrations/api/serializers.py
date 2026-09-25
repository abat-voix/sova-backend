from django.conf import settings
from rest_framework import serializers

from sova.integrations.enum import IntegrationDirection
from sova.integrations.models import IntegrationMapping
from sova.integrations.registry import ENTITIES, serializer_fields


class IntegrationMessageResponseSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    status = serializers.CharField()
    duplicate = serializers.BooleanField()


class IntegrationPayloadSerializer(serializers.Serializer):
    """Documentation-only serializer: integration payload is intentionally open-ended."""

    payload = serializers.JSONField()


class IntegrationMappingRuleSerializer(serializers.Serializer):
    sourcePath = serializers.CharField(max_length=255, allow_blank=True)
    targetField = serializers.CharField(max_length=255, allow_blank=True)
    required = serializers.BooleanField(default=False)
    defaultValue = serializers.JSONField(allow_null=True, required=False, default=None)


class IntegrationMappingSerializer(serializers.ModelSerializer):
    eventType = serializers.CharField(source="event_type", max_length=100)
    isActive = serializers.BooleanField(source="is_active", default=False)
    rules = IntegrationMappingRuleSerializer(many=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)
    updatedAt = serializers.DateTimeField(source="updated_at", read_only=True)

    class Meta:
        model = IntegrationMapping
        fields = (
            "id", "name", "system", "eventType", "direction", "entity",
            "isActive", "version", "rules", "createdAt", "updatedAt",
        )
        extra_kwargs = {"version": {"read_only": True}}

    def validate_system(self, value):
        if value not in settings.INTEGRATION_SYSTEMS:
            raise serializers.ValidationError("Неизвестная интеграционная система.")
        return value

    def validate_entity(self, value):
        if value not in ENTITIES:
            raise serializers.ValidationError("Неизвестная сущность CRM.")
        return value

    def validate(self, attrs):
        direction = attrs.get("direction", getattr(self.instance, "direction", None))
        entity = attrs.get("entity", getattr(self.instance, "entity", None))
        is_active = attrs.get("is_active", getattr(self.instance, "is_active", False))
        rules = attrs.get("rules", getattr(self.instance, "rules", []))
        fields = serializer_fields(entity) or {}
        crm_names = []
        errors = []
        for index, rule in enumerate(rules):
            source = rule["sourcePath"]
            target = rule["targetField"]
            crm_name = target if direction == IntegrationDirection.INCOMING else source
            external_path = source if direction == IntegrationDirection.INCOMING else target
            crm_names.append(crm_name)
            if crm_name not in fields:
                errors.append(f"Правило {index + 1}: поле CRM «{crm_name}» не зарегистрировано.")
            elif direction == IntegrationDirection.INCOMING and fields[crm_name].read_only:
                errors.append(f"Правило {index + 1}: поле «{crm_name}» доступно только для чтения.")
            if external_path and not external_path.startswith("$."):
                errors.append(f"Правило {index + 1}: внешний путь должен начинаться с $.")
            if rule["required"] and not external_path and rule.get("defaultValue") is None:
                errors.append(f"Правило {index + 1}: обязательному полю нужен путь или default.")
        duplicates = sorted({name for name in crm_names if crm_names.count(name) > 1})
        if duplicates:
            errors.append("CRM-поле не может использоваться дважды: " + ", ".join(duplicates))
        if is_active and not rules:
            errors.append("Активный маппинг должен содержать хотя бы одно правило.")
        if errors:
            raise serializers.ValidationError({"rules": errors})
        return attrs

    def update(self, instance, validated_data):
        validated_data["version"] = instance.version + 1
        return super().update(instance, validated_data)


class IntegrationMappingPreviewSerializer(serializers.Serializer):
    entity = serializers.ChoiceField(choices=tuple(ENTITIES))
    direction = serializers.ChoiceField(choices=IntegrationDirection.choices)
    rules = IntegrationMappingRuleSerializer(many=True)
    payload = serializers.JSONField()

    def validate(self, attrs):
        if not isinstance(attrs["payload"], dict):
            raise serializers.ValidationError({"payload": "Payload должен быть JSON-объектом."})
        mapping = IntegrationMappingSerializer(data={
            "name": "preview", "system": next(iter(settings.INTEGRATION_SYSTEMS), "lms"),
            "eventType": "preview", "direction": attrs["direction"], "entity": attrs["entity"],
            "isActive": False, "rules": attrs["rules"],
        })
        mapping.is_valid(raise_exception=True)
        return attrs


class IntegrationFieldChoiceSerializer(serializers.Serializer):
    value = serializers.JSONField()
    label = serializers.CharField()


class IntegrationFieldMetadataSerializer(serializers.Serializer):
    name = serializers.CharField()
    label = serializers.CharField()
    help_text = serializers.CharField()
    type = serializers.CharField()
    required = serializers.BooleanField()
    read_only = serializers.BooleanField()
    allow_null = serializers.BooleanField()
    many = serializers.BooleanField()
    choices = IntegrationFieldChoiceSerializer(many=True)


class IntegrationEntityMetadataSerializer(serializers.Serializer):
    code = serializers.CharField()
    label = serializers.CharField()
    serializer = serializers.CharField()
    fields = IntegrationFieldMetadataSerializer(many=True)


class IntegrationSystemSerializer(serializers.Serializer):
    code = serializers.CharField()
    label = serializers.CharField()
