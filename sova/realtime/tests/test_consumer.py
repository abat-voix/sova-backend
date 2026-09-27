from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import AnonymousUser
from django.test import TransactionTestCase, override_settings

from accounts.models import SystemRole, UserRole
from sova.core.tests.factories import UserFactory
from sova.realtime.consumers import EventsConsumer
from sova.realtime.groups import user_group_name


@override_settings(
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}},
    REALTIME_MAX_CONNECTION_AGE_SECONDS=60,
)
class EventsConsumerTestCase(TransactionTestCase):
    async def create_user(self, role: str | None = None):
        user = await database_sync_to_async(UserFactory)()
        if role is not None:
            await database_sync_to_async(UserRole.objects.create)(user=user, role=role)
        return user

    async def test_anonymous_connection_closes_with_4401(self) -> None:
        communicator = WebsocketCommunicator(EventsConsumer.as_asgi(), "/ws/events/")
        communicator.scope["user"] = AnonymousUser()

        connected, _ = await communicator.connect()

        self.assertTrue(connected)
        self.assertEqual(await communicator.receive_output(), {"type": "websocket.close", "code": 4401})

    async def test_authenticated_connection_receives_group_event_and_pong(self) -> None:
        user = await self.create_user(SystemRole.KAM)
        communicator = WebsocketCommunicator(EventsConsumer.as_asgi(), "/ws/events/")
        communicator.scope["user"] = user
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        heartbeat_id = "0199f5db-2778-7000-8000-000000000001"
        await communicator.send_json_to({"type": "ping", "id": heartbeat_id})
        self.assertEqual(await communicator.receive_json_from(), {"type": "pong", "id": heartbeat_id})

        envelope = {"version": 1, "id": "event", "type": "test", "occurred_at": "now", "data": {}}
        await get_channel_layer().group_send(
            user_group_name(user.pk),
            {"type": "realtime.event", "event": envelope},
        )
        self.assertEqual(await communicator.receive_json_from(), envelope)
        await communicator.disconnect()

    async def test_invalid_command_closes_with_4400(self) -> None:
        user = await self.create_user(SystemRole.KAM)
        communicator = WebsocketCommunicator(EventsConsumer.as_asgi(), "/ws/events/")
        communicator.scope["user"] = user
        await communicator.connect()

        await communicator.send_json_to({"type": "business-command"})

        self.assertEqual(await communicator.receive_output(), {"type": "websocket.close", "code": 4400})

    async def test_observer_connection_closes_with_4403(self) -> None:
        user = await self.create_user(SystemRole.OBSERVER)
        communicator = WebsocketCommunicator(EventsConsumer.as_asgi(), "/ws/events/")
        communicator.scope["user"] = user

        connected, _ = await communicator.connect()

        self.assertTrue(connected)
        self.assertEqual(await communicator.receive_output(), {"type": "websocket.close", "code": 4403})
