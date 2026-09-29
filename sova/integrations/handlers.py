from django.db import transaction

from sova.integrations.enum import IntegrationDirection
from sova.integrations.mapping import MappingProcessingError, apply_incoming_mapping
from sova.integrations.models import IntegrationMapping
from sova.integrations.services import enqueue_outgoing


class PermanentIntegrationHandlerError(Exception):
    pass


class TemporaryIntegrationHandlerError(Exception):
    pass


def handle_sync_requested(message) -> None:
    """Transport smoke-test handler; it deliberately creates no domain object."""
    with transaction.atomic():
        enqueue_outgoing(
            system=message.system,
            event_type="integration.sync.completed",
            external_id=f"sync-completed:{message.external_id or message.id}",
            correlation_id=message.correlation_id,
            payload={"messageId": str(message.id), "receivedEventType": message.event_type},
        )


HANDLERS = {"integration.sync.requested": handle_sync_requested}


def _active_mappings(message):
    return IntegrationMapping.objects.filter(
        system=message.system,
        event_type=message.event_type,
        direction=IntegrationDirection.INCOMING,
        is_active=True,
    )


def _save_result(message, mapping, result) -> None:
    message.mapping = mapping
    message.result = result
    message.save(update_fields=["mapping", "result", "updated_at"])


def handle_mapped_message(message) -> None:
    """Создаёт сущность CRM по маппингу: явно указанному в сообщении или единственному активному для события."""
    mapping = message.mapping
    if mapping is None:
        mappings = list(_active_mappings(message)[:2])
        if len(mappings) != 1:
            raise PermanentIntegrationHandlerError(
                f"Для события {message.event_type} должен быть ровно один активный маппинг, найдено: {len(mappings)}"
            )
        mapping = mappings[0]
    try:
        result = apply_incoming_mapping(mapping, message.payload)
    except MappingProcessingError as exc:
        result = {"created": [], "errors": exc.errors, "warnings": exc.warnings}
    _save_result(message, mapping, result)
    if result["errors"]:
        raise PermanentIntegrationHandlerError("\n".join(result["errors"]))


def resolve_handler(message):
    """Явный маппинг сообщения > кодовый обработчик события > активный маппинг события."""
    if message.mapping_id is not None:
        return handle_mapped_message
    handler = HANDLERS.get(message.event_type)
    if handler is None and _active_mappings(message).exists():
        return handle_mapped_message
    return handler
