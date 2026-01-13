import time

import pytest

from rustic_ai.core.agents.testutils import ProbeAgent
from rustic_ai.core.agents.testutils.probe_agent import PublishMixin
from rustic_ai.core.guild import agent
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.guild.g2g.boundary_agent import BoundaryAgent
from rustic_ai.core.guild.g2g.boundary_context import BoundaryContext
from rustic_ai.core.messaging import MessagingConfig
from rustic_ai.core.utils import JsonDict


class BoundaryProbeAgent(BoundaryAgent):
    """Probe agent that can observe shared inbox messages."""

    def __init__(self):
        self.received_messages = []

    @property
    def subscribe_to_shared_inbox(self) -> bool:
        return True

    @agent.processor(JsonDict)
    def collect_message(self, ctx: BoundaryContext) -> None:
        self.received_messages.append(ctx.message.model_copy(deep=True))

    def get_messages(self):
        self.received_messages.sort()
        return self.received_messages


class GatewayAgent(BoundaryAgent, PublishMixin):
    """Gateway agent that receives messages from shared inbox and forwards internally."""

    def __init__(self):
        self.processed_count = 0

    @property
    def subscribe_to_shared_inbox(self) -> bool:
        return True

    @agent.processor(JsonDict)
    def handle_incoming(self, ctx: BoundaryContext) -> None:
        """Receive messages from shared inbox and forward to internal guild topics."""
        self.processed_count += 1
        # Forward incoming message to internal guild topic using standard publish
        internal_topic = ctx.payload.get("internal_topic", "default")
        self.publish_dict(topic=internal_topic, payload=ctx.payload)


class EnvoyAgent(BoundaryAgent):
    """Envoy agent that sends messages to other guilds."""

    def __init__(self):
        self.sent_count = 0

    @property
    def subscribe_to_shared_inbox(self) -> bool:
        return False

    @agent.processor(JsonDict)
    def handle_outbound(self, ctx: BoundaryContext) -> None:
        """Send messages to other guilds."""
        self.sent_count += 1
        target_guild = ctx.payload.get("target_guild")
        if target_guild:
            # BoundaryContext is automatically provided - forward the message
            ctx.forward_out(target_guild, ctx.message)


class TestCrossGuildMessaging:
    """Test cross-guild messaging using BoundaryAgent implementations."""

    @pytest.fixture(scope="function")
    def messaging(self, request) -> MessagingConfig:
        return MessagingConfig(
            backend_module="rustic_ai.core.messaging.backend",
            backend_class="InMemoryMessagingBackend",
            backend_config={},
        )

    def test_gateway_forwards_message_across_guilds(self, messaging: MessagingConfig, database, org_id):
        """Test that a Gateway agent can forward messages to another guild's inbox."""
        # Create source guild
        source_guild_builder = GuildBuilder(
            guild_name="source_guild",
            guild_description="Source guild with envoy agent",
        ).set_messaging(
            messaging.backend_module,
            messaging.backend_class,
            messaging.backend_config,
        )

        source_guild = source_guild_builder.bootstrap(database, org_id)

        # Add Envoy to source guild to send messages out
        envoy_spec = (
            AgentBuilder(EnvoyAgent)
            .set_id("envoy")
            .set_name("EnvoyAgent")
            .set_description("Envoy for sending to other guilds")
            .add_additional_topic("requests")
            .build_spec()
        )

        envoy_agent: EnvoyAgent = source_guild._add_local_agent(envoy_spec)  # type: ignore

        # Add probe to source guild to publish requests
        probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id("probe")
            .set_name("ProbeAgent")
            .set_description("Probe in source guild")
            .build_spec()
        )

        probe_agent: ProbeAgent = source_guild._add_local_agent(probe_spec)  # type: ignore

        # Create target guild
        target_guild_builder = GuildBuilder(
            guild_name="target_guild",
            guild_description="Target guild",
        ).set_messaging(
            messaging.backend_module,
            messaging.backend_class,
            messaging.backend_config,
        )

        target_guild = target_guild_builder.bootstrap(database, org_id)

        # Add Gateway to target guild to receive messages
        gateway_spec = (
            AgentBuilder(GatewayAgent)
            .set_id("gateway")
            .set_name("GatewayAgent")
            .set_description("Gateway for receiving cross-guild messages")
            .build_spec()
        )

        gateway_agent: GatewayAgent = target_guild._add_local_agent(gateway_spec)  # type: ignore

        # Add probe to target guild to observe forwarded internal messages
        target_probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id("target_probe")
            .set_name("TargetProbeAgent")
            .set_description("Probe in target guild")
            .add_additional_topic("incoming")
            .build_spec()
        )

        target_probe: ProbeAgent = target_guild._add_local_agent(target_probe_spec)  # type: ignore

        time.sleep(0.5)

        # Publish message from source guild that envoy will send cross-guild
        # This simulates an internal agent wanting to send to another guild
        probe_agent.publish_dict(
            topic="requests",
            payload={"target_guild": target_guild.id, "data": "test_data", "internal_topic": "incoming"},
            format="test/json",
        )

        time.sleep(1.0)

        # Verify envoy sent the message
        assert envoy_agent.sent_count == 1

        # Verify gateway received and forwarded the message internally
        assert gateway_agent.processed_count == 1

        # Verify target guild's probe received the forwarded internal message
        target_messages = target_probe.get_messages()
        assert len(target_messages) >= 1
        received = [msg for msg in target_messages if msg.payload.get("data") == "test_data"]
        assert len(received) == 1
        assert received[0].topics == "incoming"

        source_guild.shutdown()
        target_guild.shutdown()

    def test_bidirectional_cross_guild_communication(self, messaging: MessagingConfig, database, org_id):
        """Test bidirectional communication between two guilds."""
        # Create Guild A with Gateway and Envoy agents
        guild_a_builder = GuildBuilder(
            guild_name="guild_a",
            guild_description="Guild A",
        ).set_messaging(
            messaging.backend_module,
            messaging.backend_class,
            messaging.backend_config,
        )

        guild_a = guild_a_builder.bootstrap(database, org_id)

        gateway_a_spec = (
            AgentBuilder(GatewayAgent)
            .set_id("gateway_a")
            .set_name("GatewayA")
            .set_description("Gateway for Guild A")
            .build_spec()
        )

        guild_a._add_local_agent(gateway_a_spec)  # type: ignore

        envoy_a_spec = (
            AgentBuilder(EnvoyAgent)
            .set_id("envoy_a")
            .set_name("EnvoyA")
            .set_description("Envoy for Guild A")
            .add_additional_topic("outbound")
            .build_spec()
        )

        envoy_a: EnvoyAgent = guild_a._add_local_agent(envoy_a_spec)  # type: ignore

        # Add probe to Guild A
        probe_a_spec = (
            AgentBuilder(ProbeAgent)
            .set_id("probe_a")
            .set_name("ProbeA")
            .set_description("Probe agent in Guild A")
            .add_additional_topic("outbound")
            .build_spec()
        )

        probe_a: ProbeAgent = guild_a._add_local_agent(probe_a_spec)  # type: ignore

        # Create Guild B with Gateway agent
        guild_b_builder = GuildBuilder(
            guild_name="guild_b",
            guild_description="Guild B",
        ).set_messaging(
            messaging.backend_module,
            messaging.backend_class,
            messaging.backend_config,
        )

        guild_b = guild_b_builder.bootstrap(database, org_id)

        gateway_b_spec = (
            AgentBuilder(GatewayAgent)
            .set_id("gateway_b")
            .set_name("GatewayB")
            .set_description("Gateway for Guild B")
            .build_spec()
        )

        gateway_b: GatewayAgent = guild_b._add_local_agent(gateway_b_spec)  # type: ignore

        # Add probe to Guild B to observe internal forwarded messages
        probe_b_spec = (
            AgentBuilder(ProbeAgent)
            .set_id("probe_b")
            .set_name("ProbeB")
            .set_description("Probe agent in Guild B")
            .add_additional_topic("internal")
            .build_spec()
        )

        probe_b: ProbeAgent = guild_b._add_local_agent(probe_b_spec)  # type: ignore

        time.sleep(0.5)

        # Send request from Guild A to Guild B via Envoy
        probe_a.publish_dict(
            topic="outbound",
            payload={
                "target_guild": guild_b.id,
                "request": "process_this",
                "internal_topic": "internal",
            },
            format="test/json",
        )

        time.sleep(1.5)

        # Verify Guild A's envoy sent the message
        assert envoy_a.sent_count == 1

        # Verify Guild B's gateway received and forwarded the message
        assert gateway_b.processed_count >= 1

        # Verify Guild B's probe saw the forwarded internal message
        probe_b_messages = probe_b.get_messages()
        b_requests = [msg for msg in probe_b_messages if msg.payload.get("request") == "process_this"]
        assert len(b_requests) >= 1

        guild_a.shutdown()
        guild_b.shutdown()

    def test_shared_namespace_activation(self, messaging: MessagingConfig, database, org_id):
        """Test that shared namespace is properly activated for boundary agents."""
        guild_builder = GuildBuilder(
            guild_name="test_shared_namespace",
            guild_description="Test guild for shared namespace",
        ).set_messaging(
            messaging.backend_module,
            messaging.backend_class,
            messaging.backend_config,
        )

        guild = guild_builder.bootstrap(database, org_id)

        gateway_spec = (
            AgentBuilder(GatewayAgent)
            .set_id("gateway_test")
            .set_name("GatewayTest")
            .set_description("Gateway test agent")
            .build_spec()
        )

        gateway_agent: GatewayAgent = guild._add_local_agent(gateway_spec)  # type: ignore

        time.sleep(0.5)

        # Verify the agent was created with organization_id
        assert hasattr(gateway_agent, "_organization_id")
        assert gateway_agent._organization_id == org_id

        # Verify the guild's messaging interface has shared namespace activated
        messaging_interface = gateway_agent._client._messaging
        assert messaging_interface.shared_namespace == org_id

        # Verify shared inbox subscription exists
        expected_topic = f"{org_id}:guild_inbox:{guild.id}"
        assert expected_topic in messaging_interface.shared_subscribers

        guild.shutdown()
