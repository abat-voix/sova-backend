from dataclasses import dataclass

from rest_framework import serializers

from sova.catalog.api.serializers import (
    B2CClientSerializer,
    ContactPersonSerializer,
    UniversitySerializer,
    WriteB2CClientSerializer,
    WriteContactPersonSerializer,
    WriteUniversitySerializer,
)
from sova.interactions.api.serializers import InteractionSerializer, WriteInteractionSerializer
from sova.processes.api.serializers import WorkflowInstanceSerializer
from sova.training.api.serializers import TrainingPaymentSerializer


@dataclass(frozen=True)
class IntegrationEntity:
    code: str
    label: str
    serializer: type[serializers.Serializer]
    # Сериализатор создания для входящих сообщений; None — сущность нельзя создать из интеграции
    write_serializer: type[serializers.Serializer] | None = None


ENTITIES = {
    entity.code: entity
    for entity in (
        IntegrationEntity("b2c_client", "B2C-клиент", B2CClientSerializer, WriteB2CClientSerializer),
        IntegrationEntity("contact_person", "Контактное лицо", ContactPersonSerializer, WriteContactPersonSerializer),
        IntegrationEntity("interaction", "Взаимодействие", InteractionSerializer, WriteInteractionSerializer),
        IntegrationEntity("university", "Университет", UniversitySerializer, WriteUniversitySerializer),
        IntegrationEntity("workflow_instance", "Экземпляр процесса", WorkflowInstanceSerializer),
        IntegrationEntity("training_payment", "Оплата обучения", TrainingPaymentSerializer, TrainingPaymentSerializer),
    )
}


def serializer_fields(entity_code: str):
    entity = ENTITIES.get(entity_code)
    return entity.serializer().fields if entity else None


def incoming_fields(entity_code: str):
    """Поля, которые входящее сообщение может заполнить: только записываемые поля сериализатора создания."""
    entity = ENTITIES.get(entity_code)
    if entity is None:
        return None
    if entity.write_serializer is None:
        return {}
    return {name: field for name, field in entity.write_serializer().fields.items() if not field.read_only}
