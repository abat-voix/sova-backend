import asyncio
import json
import logging
import uuid

from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings

from sova.realtime.groups import user_group_name


logger = logging.getLogger(__name__)
MAX_CLIENT_MESSAGE_BYTES = 4096


class EventsConsumer(AsyncWebsocketConsumer):
    group_name: str | None = None
    max_age_task: asyncio.Task | None = None

    async def connect(self) -> None:
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.accept()
            await self.close(code=4401)
            logger.info("Realtime connection rejected: unauthenticated")
            return

        self.group_name = user_group_name(user.pk)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        self.max_age_task = asyncio.create_task(self._expire_connection())
        logger.info("Realtime connection accepted user_id=%s", user.pk)

    async def disconnect(self, close_code: int) -> None:
        if self.max_age_task is not None:
            if self.max_age_task is not asyncio.current_task():
                self.max_age_task.cancel()
            self.max_age_task = None
        if self.group_name is not None:
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
            self.group_name = None
        logger.info("Realtime connection disconnected close_code=%s", close_code)

    async def receive(self, text_data: str | None = None, bytes_data: bytes | None = None) -> None:
        size = len(bytes_data) if bytes_data is not None else len((text_data or "").encode("utf-8"))
        if bytes_data is not None or size > MAX_CLIENT_MESSAGE_BYTES:
            await self.close(code=4400)
            return
        try:
            payload = json.loads(text_data or "")
        except (json.JSONDecodeError, TypeError):
            await self.close(code=4400)
            return
        if (
            not isinstance(payload, dict)
            or payload.get("type") != "ping"
            or not isinstance(payload.get("id"), str)
            or set(payload) != {"type", "id"}
        ):
            await self.close(code=4400)
            return
        try:
            uuid.UUID(payload["id"])
        except ValueError:
            await self.close(code=4400)
            return
        await self.send(text_data=json.dumps({"type": "pong", "id": payload["id"]}))

    async def realtime_event(self, event: dict) -> None:
        await self.send(text_data=json.dumps(event["event"]))

    async def _expire_connection(self) -> None:
        try:
            await asyncio.sleep(settings.REALTIME_MAX_CONNECTION_AGE_SECONDS)
            await self.close(code=4001)
        except asyncio.CancelledError:
            return
