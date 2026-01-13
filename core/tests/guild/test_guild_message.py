import importlib
import time

import pytest

from rustic_ai.core import (
    AgentTag,
    GuildTopics,
    Message,
    MessagingConfig,
    Priority,
)
from rustic_ai.core.agents.system.models import (
    UserAgentCreationRequest,
    UserAgentCreationResponse,
)
from rustic_ai.core.agents.testutils import ProbeAgent
from rustic_ai.core.agents.utils import UserProxyAgent
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.messaging import MessageConstants
from rustic_ai.core.utils import GemstoneGenerator

from core.tests.guild.simple_agent import (
    DummyMessage,
)


class TestGuildMessages:

    @pytest.fixture(scope="function")
    def messaging(self, request) -> MessagingConfig:
        return MessagingConfig(
            backend_module="rustic_ai.core.messaging.backend",
            backend_class="InMemoryMessagingBackend",
            backend_config={},
        )

    def test_message_broadcast(self, messaging: MessagingConfig, database, org_id):
        builder = GuildBuilder(
            guild_name="test_message_broadcast", guild_description="guild to test broadcast messages"
        ).set_messaging(
            messaging.backend_module,
            messaging.backend_class,
            messaging.backend_config,
        )

        guild = builder.bootstrap(database, org_id)

        time.sleep(0.5)

        user_broadcast_topic = UserProxyAgent.BROADCAST_TOPIC

        user1 = "user01"
        user1_topic = UserProxyAgent.get_user_inbox_topic(user1)
        user1_message_topic = UserProxyAgent.get_user_notifications_topic(user1)
        user1_outbox_topic = UserProxyAgent.get_user_outbox_topic(user1)
        user1_message_forward_topic = f"user_message_forward:{user1}"

        user2 = "user02"
        user2_topic = UserProxyAgent.get_user_inbox_topic(user2)
        user2_message_topic = UserProxyAgent.get_user_notifications_topic(user2)
        user2_outbox_topic = UserProxyAgent.get_user_outbox_topic(user2)

        user3 = "test_user_3"
        user3_topic = UserProxyAgent.get_user_inbox_topic(user3)
        user3_message_topic = UserProxyAgent.get_user_notifications_topic(user3)
        user3_outbox_topic = UserProxyAgent.get_user_outbox_topic(user3)

        probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id("probe_agent")
            .set_name("ProbeAgent")
            .set_description("A probe agent")
            .add_additional_topic(GuildTopics.SYSTEM_TOPIC)
            .add_additional_topic(user1_message_forward_topic)
            .add_additional_topic(user1_topic)
            .add_additional_topic(user1_message_topic)
            .add_additional_topic(user1_outbox_topic)
            .add_additional_topic(user2_topic)
            .add_additional_topic(user2_message_topic)
            .add_additional_topic(user2_outbox_topic)
            .add_additional_topic(user3_topic)
            .add_additional_topic(user3_message_topic)
            .add_additional_topic(user3_outbox_topic)
            .add_additional_topic("default_topic")
            .build_spec()
        )

        probe_agent: ProbeAgent = guild._add_local_agent(probe_spec)  # type: ignore

        probe_agent.publish_dict(
            topic=GuildTopics.SYSTEM_TOPIC,
            payload=UserAgentCreationRequest(user_id=user1, user_name=user1).model_dump(),
            format=UserAgentCreationRequest,
        )

        time.sleep(0.5)

        probe_agent.publish_dict(
            topic=GuildTopics.SYSTEM_TOPIC,
            payload=UserAgentCreationRequest(user_id=user2, user_name=user2).model_dump(),
            format=UserAgentCreationRequest,
        )

        time.sleep(0.5)

        probe_agent.publish_dict(
            topic=GuildTopics.SYSTEM_TOPIC,
            payload=UserAgentCreationRequest(user_id=user3, user_name=user3).model_dump(),
            format=UserAgentCreationRequest,
        )

        time.sleep(0.5)

        probe_agent_messages = probe_agent.get_messages()

        assert len(probe_agent_messages) == 3

        user_agent_creation_response = UserAgentCreationResponse.model_validate(probe_agent_messages[0].payload)

        for message in probe_agent_messages:
            user_agent_creation_response = UserAgentCreationResponse.model_validate(message.payload)
            assert user_agent_creation_response.status_code == 201

        probe_agent.clear_messages()

        # Test that all agents get an forward the message on broadcast topic

        msg_id = probe_agent.publish_dict(
            topic=user_broadcast_topic,
            payload={"message": "Broadcast message"},
            format=MessageConstants.RAW_JSON_FORMAT,
        )

        msg_id_int = msg_id.to_int()

        time.sleep(1.0)  # Wait for message delivery

        probe_agent_messages = probe_agent.get_messages()

        assert len(probe_agent_messages) == 3

        for message in probe_agent_messages:
            assert message.payload["message"] == "Broadcast message"
            assert message.topics is not None
            assert isinstance(message.topics, str)
            topic_type, user_id = message.topics.split(":")
            assert topic_type == "user_notifications"
            assert UserProxyAgent.get_user_agent_id(user_id) == message.sender.id
            assert message.forward_header is not None
            assert message.forward_header.origin_message_id == msg_id_int
            assert message.forward_header.on_behalf_of.name == "ProbeAgent"

        probe_agent.clear_messages()

        # Test that incoming messages are forwarded to the broadcast topic

        gemgen = GemstoneGenerator(100)

        send_id = gemgen.get_id(Priority.NORMAL)

        wrapped_message = Message(
            id_obj=send_id,
            topics="default_topic",
            sender=AgentTag(id="dummyUserId", name="dummy_user"),
            payload={"message": "Hello, world!"},
        )

        probe_agent.publish_dict(
            topic=user1_topic,
            payload=wrapped_message.model_dump(),
            format=Message,
            msg_id=send_id,
        )

        time.sleep(1.0)  # Wait for message delivery

        probe_agent_messages = probe_agent.get_messages()

        assert len(probe_agent_messages) == 4

        default_topic_messages = [message for message in probe_agent_messages if message.topics == "default_topic"]

        assert len(default_topic_messages) == 1

        default_topic_message = default_topic_messages[0]

        assert default_topic_message.payload["message"] == "Hello, world!"
        assert default_topic_message.sender.id == UserProxyAgent.get_user_agent_id(user1)

        user_notifications = [
            message
            for message in probe_agent_messages
            if message.topics is not None
            and isinstance(message.topics, str)
            and message.topics.startswith("user_notifications")
        ]

        assert len(user_notifications) == 3

        notified_users = []
        for message in user_notifications:
            assert message.payload["message"] == "Hello, world!"
            assert message.topics is not None
            assert isinstance(message.topics, str)
            _, user_id = message.topics.split(":")
            assert message.sender.id == UserProxyAgent.get_user_agent_id(user_id)
            if message.forward_header:
                assert message.forward_header.origin_message_id == send_id.to_int()
                assert message.forward_header.on_behalf_of.name == "ProbeAgent"
                notified_users.append(user_id)

    def test_messages_with_reason(self, messaging: MessagingConfig, org_id):
        json_path = importlib.resources.files("core.tests.resources.guild_specs").joinpath("test_reason_guild.json")
        builder = GuildBuilder.from_json_file(json_path)
        builder.set_messaging(
            messaging.backend_module,
            messaging.backend_class,
            messaging.backend_config,
        )
        guild = builder.launch(org_id)

        probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id("probe_agent")
            .set_name("ProbeAgent")
            .set_description("A probe agent")
            .add_additional_topic(GuildTopics.DEFAULT_TOPICS[0])
            .add_additional_topic(GuildTopics.ERROR_TOPIC)
            .build_spec()
        )

        probe_agent: ProbeAgent = guild._add_local_agent(probe_spec)  # type: ignore

        probe_agent.publish_dict("test_topic", DummyMessage(key1="jkl", key2=789), routing_slip=guild.routes)

        time.sleep(1)

        messages = probe_agent.get_messages()
        assert len(messages) == 1
        dummy_response = messages[0]
        response_history = dummy_response.message_history[-1]
        assert len(response_history.reason) == 2
        assert "Identified payload as DummyMessage" in response_history.reason
        assert "simply doing my job" in response_history.reason
