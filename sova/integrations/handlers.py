from django.db import transaction

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
