from dataclasses import dataclass
from uuid import UUID, uuid4

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from sova.integrations.enum import IntegrationDirection, IntegrationStatus
from sova.integrations.models import IntegrationMapping, IntegrationMessage


@dataclass(frozen=True)
class ReceiveResult:
    message: IntegrationMessage
    duplicate: bool


def _normalise(value: str) -> str:
    return value.strip()


def _check_system(system: str) -> None:
    if system not in settings.INTEGRATION_SYSTEMS:
        raise ValueError(f"Unknown integration system: {system}")


def _schedule(message: IntegrationMessage) -> None:
    from sova.integrations.tasks import process_incoming_message, send_outgoing_message

    task = process_incoming_message if message.direction == IntegrationDirection.INCOMING else send_outgoing_message
    task.apply_async(args=[str(message.pk)], queue="integrations")


def receive_message(*, system: str, event_type: str, payload: dict, external_id: str = "", correlation_id: UUID | None = None) -> ReceiveResult:
    system, event_type, external_id = map(_normalise, (system, event_type, external_id))
    _check_system(system)
    if not isinstance(payload, dict):
        raise ValueError("Integration payload must be an object")
    correlation_id = correlation_id or uuid4()
    try:
        with transaction.atomic():
            message = IntegrationMessage.objects.create(
                system=system,
                direction=IntegrationDirection.INCOMING,
                event_type=event_type or "generic.received",
                external_id=external_id,
                correlation_id=correlation_id,
                payload=payload,
                status=IntegrationStatus.PENDING,
            )
            transaction.on_commit(lambda: _schedule(message))
    except IntegrityError:
        if not external_id:
            raise
        message = IntegrationMessage.objects.get(
            system=system, direction=IntegrationDirection.INCOMING, external_id=external_id
        )
        return ReceiveResult(message=message, duplicate=True)
    return ReceiveResult(message=message, duplicate=False)


def enqueue_outgoing(*, system: str, event_type: str, payload: dict, external_id: str, correlation_id: UUID | None = None) -> IntegrationMessage:
    system, event_type, external_id = map(_normalise, (system, event_type, external_id))
    _check_system(system)
    if not external_id:
        raise ValueError("external_id is required for outgoing messages")
    if not isinstance(payload, dict):
        raise ValueError("Integration payload must be an object")
    try:
        with transaction.atomic():
            message = IntegrationMessage.objects.create(
                system=system,
                direction=IntegrationDirection.OUTGOING,
                event_type=event_type,
                external_id=external_id,
                correlation_id=correlation_id or uuid4(),
                payload=payload,
                status=IntegrationStatus.PENDING,
            )
            transaction.on_commit(lambda: _schedule(message))
            return message
    except IntegrityError:
        return IntegrationMessage.objects.get(
            system=system, direction=IntegrationDirection.OUTGOING, external_id=external_id
        )


def process_with_mapping(*, mapping: IntegrationMapping, payload: dict) -> IntegrationMessage:
    """Ручная загрузка JSON (объект или массив): сообщение фиксируется в журнале и разбирается маппингом сразу, без очереди."""
    from sova.integrations.handlers import handle_mapped_message

    if mapping.direction != IntegrationDirection.INCOMING:
        raise ValueError("Загрузить JSON можно только во входящий маппинг")
    if not isinstance(payload, (dict, list)):
        raise ValueError("Integration payload must be an object or an array")
    message = IntegrationMessage.objects.create(
        system=mapping.system,
        direction=IntegrationDirection.INCOMING,
        event_type=mapping.event_type,
        mapping=mapping,
        payload=payload,
        status=IntegrationStatus.PROCESSING,
        attempts=1,
    )
    try:
        handle_mapped_message(message)
    except Exception as exc:
        message.status = IntegrationStatus.FAILED
        message.last_error = str(exc)[:2000]
    else:
        message.status = IntegrationStatus.PROCESSED
        message.processed_at = timezone.now()
    message.save(update_fields=["status", "last_error", "processed_at", "updated_at"])
    return message
