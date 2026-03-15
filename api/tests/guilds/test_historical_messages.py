from typing import List

import pytest

from rustic_ai.api_server.guilds.comms_manager import GuildCommunicationManager
from rustic_ai.core.messaging.core.message import AgentTag, Message
from rustic_ai.core.utils.gemstone_id import GemstoneID
from rustic_ai.core.utils.priority import Priority


def _make_message(
    *,
    timestamp: int,
    machine_id: int,
    sequence: int,
    sender: AgentTag,
    content: str,
    thread: List[int] | None = None,
    in_response_to: int | None = None,
) -> Message:
    return Message(
        id_obj=GemstoneID(Priority.NORMAL, timestamp, machine_id, sequence),
        topics="user_message_broadcast",
        sender=sender,
        payload={"content": content},
        thread=thread or [],
        in_response_to=in_response_to,
    )


class _FakeMessagingInterface:
    def __init__(self, user_messages: List[Message], broadcast_messages: List[Message]):
        self._user_messages = user_messages
        self._broadcast_messages = broadcast_messages

    def get_messages(self, topic: str) -> List[Message]:
        if topic.startswith("user_notifications:"):
            return self._user_messages
        if topic == "user_message_broadcast":
            return self._broadcast_messages
        raise AssertionError(f"Unexpected topic requested: {topic}")


@pytest.mark.asyncio
async def test_get_historical_user_notifications_orders_broadcast_messages_causally(monkeypatch):
    manager = GuildCommunicationManager()
    timestamp = 1_750_000_000_000

    user_message = _make_message(
        timestamp=timestamp,
        machine_id=200,
        sequence=0,
        sender=AgentTag(id="upa-user123", name="user_name_123"),
        content="Hello, guild 3!",
    )
    echo_message = _make_message(
        timestamp=timestamp,
        machine_id=1,
        sequence=0,
        sender=AgentTag(id="echo-agent", name="EchoAgent"),
        content="Hello, guild 3!",
        thread=[user_message.id],
        in_response_to=user_message.id,
    )

    # Sorting by raw ID alone would put the echo response first here.
    assert echo_message.id < user_message.id

    fake_messaging = _FakeMessagingInterface(
        user_messages=[],
        broadcast_messages=[echo_message, user_message],
    )

    async def fake_get_or_fetch_guild_spec(self, guild_id, engine):
        return object()

    async def fake_get_or_create_messaging_interface(self, guild_spec):
        return fake_messaging

    monkeypatch.setattr(GuildCommunicationManager, "get_or_fetch_guild_spec", fake_get_or_fetch_guild_spec)
    monkeypatch.setattr(
        GuildCommunicationManager,
        "get_or_create_messaging_interface",
        fake_get_or_create_messaging_interface,
    )

    messages = await manager.get_historical_user_notifications("guild-1", "user234", engine=None)

    assert [message.sender.name for message in messages] == ["user_name_123", "EchoAgent"]
    assert [message.payload["content"] for message in messages] == ["Hello, guild 3!", "Hello, guild 3!"]
