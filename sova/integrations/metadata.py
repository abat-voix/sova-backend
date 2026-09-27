"""Metadata for the CRM fields exposed to integration mapping configuration."""

from importlib import import_module

from rest_framework import serializers


# Only serializers explicitly listed here become available for integration mapping.
# This is intentionally an allow-list, not automatic discovery of every Django model.
INTEGRATION_SERIALIZERS = {
    "workflow": {
        "label": "Workflow",
        "serializer": "sova.workflows.api.serializers.workflow.WorkflowSerializer",
    },
    "workflow_instance": {
        "label": "Экземпляр workflow",
        "serializer": "sova.processes.api.serializers.workflow_instance.WorkflowInstanceSerializer",
    },
    "interaction": {
        "label": "Взаимодействие",
        "serializer": "sova.interactions.api.serializers.interaction.InteractionSerializer",
    },
}


def _load_class(path: str):
    module_path, class_name = path.rsplit(".", 1)
    return getattr(import_module(module_path), class_name)


def _field_type(field) -> str:
    if isinstance(field, serializers.ListSerializer) or getattr(field, "many", False):
        return "array"
    if isinstance(field, serializers.BooleanField):
        return "boolean"
    if isinstance(field, serializers.IntegerField):
        return "integer"
    if isinstance(field, serializers.FloatField):
        return "number"
    if isinstance(field, serializers.DecimalField):
        return "decimal"
    if isinstance(field, serializers.UUIDField):
        return "uuid"
    if isinstance(field, serializers.DateTimeField):
        return "datetime"
    if isinstance(field, serializers.DateField):
        return "date"
    if isinstance(field, serializers.JSONField):
        return "json"
    if isinstance(field, serializers.DictField):
        return "object"
    if isinstance(field, (serializers.ListField,)):
        return "array"
    if isinstance(field, serializers.PrimaryKeyRelatedField):
        return "relation"
    if isinstance(field, serializers.Serializer):
        return "object"
    if isinstance(field, serializers.ChoiceField):
        return "choice"
    return "string"


def _choices(field):
    if not isinstance(field, serializers.ChoiceField):
        return []
    return [{"value": value, "label": str(label)} for value, label in field.choices.items()]


def entity_metadata(code: str, definition: dict) -> dict:
    serializer_class = _load_class(definition["serializer"])
    serializer = serializer_class()
    fields = []
    for name, field in serializer.fields.items():
        fields.append(
            {
                "name": name,
                "label": str(field.label or name),
                "help_text": str(field.help_text or ""),
                "type": _field_type(field),
                "required": field.required,
                "read_only": field.read_only,
                "allow_null": field.allow_null,
                "many": getattr(field, "many", False),
                "choices": _choices(field),
            }
        )
    return {
        "code": code,
        "label": definition["label"],
        "serializer": definition["serializer"],
        "fields": fields,
    }


def all_entities() -> list[dict]:
    return [entity_metadata(code, definition) for code, definition in INTEGRATION_SERIALIZERS.items()]
