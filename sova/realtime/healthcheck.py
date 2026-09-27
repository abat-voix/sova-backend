"""Readiness probe for the dedicated Daphne process and Channels Redis layer."""

import asyncio
import json
import logging
import os
import secrets
import urllib.request

from channels.layers import get_channel_layer


logger = logging.getLogger(__name__)
PROBE_TIMEOUT_SECONDS = 3


def _check_http() -> None:
    allowed_hosts = [host.strip() for host in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost").split(",")]
    host = next((item for item in allowed_hosts if item and item != "*"), "localhost")
    request = urllib.request.Request(
        "http://127.0.0.1:8000/api/health/",
        headers={"Host": host, "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=PROBE_TIMEOUT_SECONDS) as response:
        if response.status != 200:
            raise RuntimeError(f"Daphne HTTP readiness returned {response.status}.")
        result = json.loads(response.read())
        if result.get("status") != "ok":
            raise RuntimeError("Daphne HTTP readiness reported an unhealthy dependency.")


async def _check_channel_layer() -> None:
    channel_layer = get_channel_layer()
    if channel_layer is None:
        raise RuntimeError("Default Channels layer is not configured.")

    channel_name = await channel_layer.new_channel("sova_health")
    token = secrets.token_urlsafe(24)
    try:
        await asyncio.wait_for(
            channel_layer.send(channel_name, {"type": "health.probe", "token": token}),
            timeout=PROBE_TIMEOUT_SECONDS,
        )
        response = await asyncio.wait_for(
            channel_layer.receive(channel_name),
            timeout=PROBE_TIMEOUT_SECONDS,
        )
        if response.get("type") != "health.probe" or response.get("token") != token:
            raise RuntimeError("Channels Redis probe returned an unexpected message.")
    finally:
        close = getattr(channel_layer, "close_pools", None)
        if close is not None:
            await close()


async def _check() -> None:
    await asyncio.wait_for(asyncio.to_thread(_check_http), timeout=PROBE_TIMEOUT_SECONDS + 1)
    await _check_channel_layer()


def main() -> int:
    try:
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sova.settings")
        import django

        django.setup()
        asyncio.run(_check())
    except Exception:
        logger.exception("Realtime readiness check failed.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
