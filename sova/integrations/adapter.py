import json
from datetime import timezone as dt_timezone

import requests
from django.conf import settings


class IntegrationAdapterError(Exception):
    """Base error raised by the outbound HTTP adapter."""


class TemporaryIntegrationError(IntegrationAdapterError):
    pass


class PermanentIntegrationError(IntegrationAdapterError):
    pass


def _short_response(response) -> str:
    text = (response.text or "").replace("\x00", "")
    return f"HTTP {response.status_code}: {text[:1900]}"


def send(message) -> None:
    config = settings.INTEGRATION_SYSTEMS.get(message.system)
    if not config or not config.get("url"):
        raise PermanentIntegrationError(f"Integration URL is not configured: {message.system}")
    token = config.get("outbound_token", "")
    if not token:
        raise PermanentIntegrationError(f"Integration outbound token is not configured: {message.system}")

    occurred_at = message.created_at.astimezone(dt_timezone.utc).isoformat().replace("+00:00", "Z")
    envelope = {
        "eventId": message.external_id,
        "eventType": message.event_type,
        "eventVersion": 1,
        "source": "crm",
        "destination": message.system,
        "occurredAt": occurred_at,
        "correlationId": str(message.correlation_id),
        "data": message.payload,
    }
    try:
        body = json.dumps(envelope, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise PermanentIntegrationError(f"Payload is not JSON serializable: {exc}") from exc

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Idempotency-Key": message.external_id,
    }
    try:
        response = requests.post(
            config["url"],
            json=envelope,
            headers=headers,
            timeout=settings.INTEGRATION_HTTP_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise TemporaryIntegrationError(f"HTTP request failed: {str(exc)[:1900]}") from exc

    if 200 <= response.status_code < 300:
        return
    if response.status_code in {408, 425, 429} or response.status_code >= 500:
        raise TemporaryIntegrationError(_short_response(response))
    raise PermanentIntegrationError(_short_response(response))
