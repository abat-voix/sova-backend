from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from datetime import timedelta

from sova.integrations import adapter
from sova.integrations.enum import IntegrationDirection, IntegrationStatus
from sova.integrations.handlers import (
    HANDLERS,
    PermanentIntegrationHandlerError,
    TemporaryIntegrationHandlerError,
)
from sova.integrations.models import IntegrationMessage


RETRY_DELAYS = (60, 300, 900, 3600)


def _start(message_id: str, direction: str):
    with transaction.atomic():
        message = IntegrationMessage.objects.select_for_update().get(pk=message_id)
        if message.direction != direction or message.status in {
            IntegrationStatus.PROCESSED, IntegrationStatus.IGNORED, IntegrationStatus.FAILED
        }:
            return None
        message.status = IntegrationStatus.PROCESSING
        message.attempts += 1
        message.next_retry_at = None
        message.save(update_fields=["status", "attempts", "next_retry_at", "updated_at"])
        return message


def _success(message_id: str, status=IntegrationStatus.PROCESSED, error=""):
    values = {"status": status, "last_error": error, "updated_at": timezone.now()}
    if status == IntegrationStatus.PROCESSED:
        values["processed_at"] = timezone.now()
    IntegrationMessage.objects.filter(pk=message_id).update(**values)


def _failure(self, message, error: Exception, *, retryable: bool):
    detail = str(error)[:2000]
    if retryable and message.attempts < settings.INTEGRATION_MAX_ATTEMPTS:
        delay = RETRY_DELAYS[min(message.attempts - 1, len(RETRY_DELAYS) - 1)]
        IntegrationMessage.objects.filter(pk=message.pk).update(
            status=IntegrationStatus.RETRY,
            next_retry_at=timezone.now() + timedelta(seconds=delay),
            last_error=detail,
            updated_at=timezone.now(),
        )
        raise self.retry(exc=error, countdown=delay, max_retries=settings.INTEGRATION_MAX_ATTEMPTS - 1)
    IntegrationMessage.objects.filter(pk=message.pk).update(
        status=IntegrationStatus.FAILED, last_error=detail, next_retry_at=None, updated_at=timezone.now()
    )


@shared_task(bind=True, acks_late=True, max_retries=None)
def process_incoming_message(self, message_id: str) -> None:
    message = _start(message_id, IntegrationDirection.INCOMING)
    if message is None:
        return
    handler = HANDLERS.get(message.event_type)
    if handler is None:
        _success(message.pk, IntegrationStatus.IGNORED, f"No handler for event type: {message.event_type}")
        return
    try:
        handler(message)
    except PermanentIntegrationHandlerError as exc:
        _failure(self, message, exc, retryable=False)
    except TemporaryIntegrationHandlerError as exc:
        _failure(self, message, exc, retryable=True)
    except Exception as exc:
        _failure(self, message, exc, retryable=False)
    else:
        _success(message.pk)


@shared_task(bind=True, acks_late=True, max_retries=None)
def send_outgoing_message(self, message_id: str) -> None:
    message = _start(message_id, IntegrationDirection.OUTGOING)
    if message is None:
        return
    try:
        adapter.send(message)
    except adapter.TemporaryIntegrationError as exc:
        _failure(self, message, exc, retryable=True)
    except adapter.PermanentIntegrationError as exc:
        _failure(self, message, exc, retryable=False)
    else:
        _success(message.pk)


@shared_task
def dispatch_pending_integration_messages() -> int:
    now = timezone.now()
    with transaction.atomic():
        messages = list(
            IntegrationMessage.objects.select_for_update(skip_locked=True)
            .filter(status=IntegrationStatus.PENDING)
            .order_by("created_at")[:100]
        )
        messages += list(
            IntegrationMessage.objects.select_for_update(skip_locked=True)
            .filter(status=IntegrationStatus.RETRY, next_retry_at__lte=now)
            .order_by("created_at")[: max(0, 100 - len(messages))]
        )
    for message in messages:
        _schedule_task(message)
    return len(messages)


def _schedule_task(message):
    task = process_incoming_message if message.direction == IntegrationDirection.INCOMING else send_outgoing_message
    task.apply_async(args=[str(message.pk)], queue="integrations")
