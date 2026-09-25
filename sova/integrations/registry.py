from dataclasses import dataclass

from rest_framework import serializers

from sova.catalog.api.serializers import (
    B2CClientSerializer,
    ContactPersonSerializer,
    UniversitySerializer,
)
from sova.interactions.api.serializers import InteractionSerializer
from sova.processes.api.serializers import WorkflowInstanceSerializer


@dataclass(frozen=True)
class IntegrationEntity:
    code: str
    label: str
    serializer: type[serializers.Serializer]


ENTITIES = {
    entity.code: entity
    for entity in (
        IntegrationEntity("b2c_client", "B2C-клиент", B2CClientSerializer),
        IntegrationEntity("contact_person", "Контактное лицо", ContactPersonSerializer),
        IntegrationEntity("interaction", "Взаимодействие", InteractionSerializer),
        IntegrationEntity("university", "Университет", UniversitySerializer),
        IntegrationEntity("workflow_instance", "Экземпляр процесса", WorkflowInstanceSerializer),
    )
}


def serializer_fields(entity_code: str):
    entity = ENTITIES.get(entity_code)
    return entity.serializer().fields if entity else None
