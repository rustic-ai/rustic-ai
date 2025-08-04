from datetime import datetime
import os
import time

import pytest
import shortuuid

from rustic_ai.core.agents.testutils.echo_agent import EchoAgent
from rustic_ai.core.agents.testutils.probe_agent import EssentialProbeAgent
from rustic_ai.core.guild.agent_ext.mixins.health import (
    HealthCheckRequest,
    HealthConstants,
    HeartbeatStatus,
)
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.guild.dsl import AgentSpec, GuildTopics
from rustic_ai.core.guild.metastore.database import Metastore
from rustic_ai.core.messaging.core.messaging_config import MessagingConfig


class TestHealthMixin:

    @pytest.fixture(scope="module")
    def messaging_server(self):
        """Start a single embedded messaging server for all tests in this module."""
        import asyncio
        import threading
        import time

        from rustic_ai.core.messaging.backend.embedded_backend import EmbeddedServer

        port = 31149
        server = EmbeddedServer(port=port)

        def run_server():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(server.start())
            try:
                loop.run_forever()
            except KeyboardInterrupt:
                pass
            finally:
                loop.run_until_complete(server.stop())
                loop.close()

        thread = threading.Thread(target=run_server, daemon=True)
        thread.start()
        time.sleep(0.5)  # Wait for server to start

        yield server, port

        # Clean up
        if server.running:
            server.topics.clear()
            server.messages.clear()
            server.subscribers.clear()

    @pytest.fixture
    def messaging_config(self, messaging_server):
        # Use embedded backend for multiprocess tests (in-memory can't work across processes)
        # Connect to the shared server started by the messaging_server fixture
        server, port = messaging_server
        return MessagingConfig(
            backend_module="rustic_ai.core.messaging.backend.embedded_backend",
            backend_class="EmbeddedMessagingBackend",
            backend_config={"port": port, "auto_start_server": False},
        )

    @pytest.fixture
    def echo_agent(self) -> AgentSpec:
        name = "EchoAgent"
        description = "An echo agent"
        additional_topic = "echo_topic"
        return (
            AgentBuilder(EchoAgent)
            .set_name(name)
            .set_description(description)
            .add_additional_topic(additional_topic)
            .listen_to_default_topic(False)
            .build_spec()
        )

    @pytest.fixture
    def guild_id(self):
        return f"test_guild_id_{shortuuid.uuid()}"

    @pytest.fixture
    def guild_name(self):
        return "test_guild_name"

    @pytest.fixture
    def guild_description(self, guild_name):
        return f"description for {guild_name}"

    @pytest.fixture
    def database(self):
        db = "sqlite:///test_rustic_app.db"

        if os.path.exists("test_rustic_app.db"):
            os.remove("test_rustic_app.db")

        Metastore.initialize_engine(db)
        Metastore.get_engine(db)
        Metastore.create_db()
        yield db
        Metastore.drop_db()

    def test_health_mixin(
        self, guild_id, guild_name, guild_description, echo_agent, database, org_id, messaging_config: MessagingConfig
    ):
        builder = GuildBuilder(guild_id, guild_name, guild_description).add_agent_spec(echo_agent)

        guild = builder.bootstrap(database, org_id)

        time.sleep(1)

        probe_spec = (
            AgentBuilder(EssentialProbeAgent)
            .set_id("probe_agent")
            .set_name("ProbeAgent")
            .set_description("A probe agent")
            .add_additional_topic(GuildTopics.SYSTEM_TOPIC)
            .add_additional_topic("default_topic")
            .build_spec()
        )

        probe_agent = guild._add_local_agent(probe_spec)

        assert probe_agent._client is not None
        assert probe_agent._client._messaging is not None

        msging = probe_agent._client._messaging

        heartbeat = HealthCheckRequest(checktime=datetime.now())
        isotime = heartbeat.checktime.isoformat()

        msg_id = probe_agent.publish_dict(
            topic=HealthConstants.HEARTBEAT_TOPIC,
            payload=heartbeat.model_dump(),
            format=HealthCheckRequest,
        ).to_int()

        time.sleep(2)

        self_messages = msging.get_messages_for_topic_since(
            GuildTopics.get_self_agent_inbox(echo_agent.id),
            0,
        )

        print(f"self_messages: {[sm.model_dump() for sm in self_messages]}")

        # Assert that the echo agent received the expected SelfReadyNotification on its self topic
        assert len(self_messages) == 1, f"Expected exactly 1 self message, got {len(self_messages)}"
        assert self_messages[0].format == "rustic_ai.core.guild.agent.SelfReadyNotification"

        status_messages = msging.get_messages_for_topic_since(
            GuildTopics.GUILD_STATUS_TOPIC,
            0,
        )

        print(f"status_messages: {[sm.model_dump() for sm in status_messages]}")

        # Assert that there are guild status messages with AgentsHealthReport
        assert len(status_messages) > 0, "Expected at least one status message"
        assert all(
            msg.format == "rustic_ai.core.guild.agent_ext.mixins.health.AgentsHealthReport" for msg in status_messages
        ), "All status messages should be AgentsHealthReport format"

        # Verify that we have health reports showing the echo agent
        echo_agent_reports = [
            msg
            for msg in status_messages
            if isinstance(msg.payload, dict) and echo_agent.id in msg.payload.get("agents", {})
        ]
        assert len(echo_agent_reports) > 0, f"Expected health reports containing echo agent {echo_agent.id}"

        # Verify that the final health status shows 'ok' for the guild
        final_status_msg = status_messages[-1]
        assert isinstance(final_status_msg.payload, dict), "Status message payload should be a dict"
        assert (
            final_status_msg.payload.get("guild_health") == "ok"
        ), f"Expected final guild health to be 'ok', got '{final_status_msg.payload.get('guild_health')}'"

        # Verify that the echo agent eventually shows 'ok' status
        agents_data = final_status_msg.payload.get("agents", {})
        assert isinstance(agents_data, dict), "Agents data should be a dict"
        final_echo_status = agents_data.get(echo_agent.id, {})
        assert isinstance(final_echo_status, dict), "Echo agent status should be a dict"
        assert (
            final_echo_status.get("checkstatus") == "ok"
        ), f"Expected echo agent final status to be 'ok', got '{final_echo_status.get('checkstatus')}'"

        health_messages = msging.get_messages_for_topic_since(
            HealthConstants.HEARTBEAT_TOPIC,
            0,
        )
        print(f"health_messages: {[sm.model_dump() for sm in health_messages]}")

        # Assert that health messages contain the heartbeat request and responses
        assert len(health_messages) >= 3  # Should have multiple heartbeat-related messages

        # Separate HealthCheckRequest messages from Heartbeat response messages
        request_messages = [
            msg
            for msg in health_messages
            if msg.format == "rustic_ai.core.guild.agent_ext.mixins.health.HealthCheckRequest"
        ]
        response_messages = [
            msg for msg in health_messages if msg.format == "rustic_ai.core.guild.agent_ext.mixins.health.Heartbeat"
        ]

        # Verify we have both request and response messages
        assert len(request_messages) >= 1, f"Expected at least 1 HealthCheckRequest, got {len(request_messages)}"
        assert len(response_messages) >= 2, f"Expected at least 2 Heartbeat responses, got {len(response_messages)}"

        # Verify that our original request is among the HealthCheckRequest messages
        our_request = next((msg for msg in request_messages if msg.payload["checktime"] == isotime), None)
        assert our_request is not None, f"Could not find our HealthCheckRequest with checktime {isotime}"

        messages = probe_agent.get_messages()
        # Filter for only heartbeat responses, not SelfReadyNotification
        heartbeat_messages = [
            msg for msg in messages if msg.format == "rustic_ai.core.guild.agent_ext.mixins.health.Heartbeat"
        ]
        assert len(heartbeat_messages) == 2

        mpair = {msg.sender.name: msg for msg in heartbeat_messages}

        manager_name = f"GuildManagerAgent4{guild.id}"

        assert "EchoAgent" in mpair
        assert manager_name in mpair

        echo_message = mpair["EchoAgent"]
        assert echo_message.format == "rustic_ai.core.guild.agent_ext.mixins.health.Heartbeat"
        assert echo_message.in_response_to == msg_id
        assert echo_message.payload["checktime"] == isotime
        assert echo_message.payload["checkstatus"] == HeartbeatStatus.OK.value
        assert echo_message.topic_published_to == HealthConstants.HEARTBEAT_TOPIC

        manager_message = mpair[manager_name]
        assert manager_message.format == "rustic_ai.core.guild.agent_ext.mixins.health.Heartbeat"
        assert manager_message.in_response_to == msg_id
        assert manager_message.payload["checktime"] == isotime
        assert manager_message.payload["checkstatus"] == HeartbeatStatus.OK.value
        assert manager_message.topic_published_to == HealthConstants.HEARTBEAT_TOPIC

        probe_agent.clear_messages()

        guild.shutdown()
