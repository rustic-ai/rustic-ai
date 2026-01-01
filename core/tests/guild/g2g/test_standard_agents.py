"""
Tests for standard Gateway and Envoy agents.

These tests verify the standard GatewayAgent and EnvoyAgent implementations.

GatewayAgent: Server-like agent that accepts messages from external guilds.
- Receives messages from any source guild (subject to allowed_source_guilds filter)
- Source guild is extracted from message's origin_guild_stack
- Forwards accepted messages internally
- Routes returned responses back through the origin_guild_stack chain

EnvoyAgent: Outbound-only agent with 1-1 mapping to a target guild.
- Forwards messages to its configured target_guild
"""

import time

import pytest

from rustic_ai.core.agents.testutils import ProbeAgent
from rustic_ai.core.guild import Agent, agent
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.guild.g2g import (
    EnvoyAgent,
    EnvoyAgentProps,
    GatewayAgent,
    GatewayAgentProps,
)
from rustic_ai.core.guild.g2g.boundary_agent import BoundaryAgent
from rustic_ai.core.guild.g2g.boundary_context import BoundaryContext
from rustic_ai.core.messaging import MessagingConfig
from rustic_ai.core.utils import JsonDict


class ResponderAgent(Agent):
    """Internal agent that processes requests and sends responses."""

    def __init__(self):
        self.received_requests = []

    @agent.processor(JsonDict, predicate=lambda self, msg: msg.format == "request/json")
    def handle_request(self, ctx: agent.ProcessContext[JsonDict]) -> None:
        """Process request and send a response."""
        self.received_requests.append(ctx.payload)
        # Send response using ctx.send_dict which properly carries forward
        # the origin_guild_stack for routing back through the chain
        ctx.send_dict(
            payload={
                "response_to": ctx.payload.get("request_id"),
                "result": f"processed_{ctx.payload.get('data')}",
            },
            format="response/json",
        )


class TestStandardAgents:
    """Test standard Gateway and Envoy agent implementations."""

    @pytest.fixture(
        scope="function",
        params=[
            pytest.param("InMemoryMessagingBackend", id="InMemoryMessagingBackend"),
            pytest.param("EmbeddedMessagingBackend", id="EmbeddedMessagingBackend"),
        ],
    )
    def messaging(self, request, messaging_server) -> MessagingConfig:
        backend_type = request.param

        if backend_type == "InMemoryMessagingBackend":
            return MessagingConfig(
                backend_module="rustic_ai.core.messaging.backend",
                backend_class="InMemoryMessagingBackend",
                backend_config={},
            )
        elif backend_type == "EmbeddedMessagingBackend":
            server, port = messaging_server
            return MessagingConfig(
                backend_module="rustic_ai.core.messaging.backend.embedded_backend",
                backend_class="EmbeddedMessagingBackend",
                backend_config={"auto_start_server": False, "port": port},
            )
        else:
            raise ValueError(f"Unknown backend type: {backend_type}")

    def test_standard_gateway_and_envoy_cross_guild(self, messaging: MessagingConfig, database, org_id):
        """Test standard GatewayAgent and EnvoyAgent for cross-guild messaging.

        Setup:
        - Source guild has EnvoyAgent configured to send to target_guild
        - Target guild has GatewayAgent that accepts messages from any source
        """
        # Create source guild
        source_guild = (
            GuildBuilder(guild_name="source_guild", guild_description="Source")
            .set_messaging(messaging.backend_module, messaging.backend_class, messaging.backend_config)
            .bootstrap(database, org_id)
        )

        # Create target guild with gateway
        target_guild = (
            GuildBuilder(guild_name="target_guild", guild_description="Target")
            .set_messaging(messaging.backend_module, messaging.backend_class, messaging.backend_config)
            .bootstrap(database, org_id)
        )

        # Gateway accepts messages from any source guild
        gateway_spec = (
            AgentBuilder(GatewayAgent)
            .set_id("gateway")
            .set_name("Gateway")
            .set_description("Gateway for cross-guild messages")
            .build_spec()
        )
        target_guild._add_local_agent(gateway_spec)

        # Probe listens to default topic to see forwarded messages
        target_probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id("target_probe")
            .set_name("TargetProbe")
            .set_description("Probe in target guild")
            .build_spec()
        )
        target_probe: ProbeAgent = target_guild._add_local_agent(target_probe_spec)  # type: ignore

        # Add EnvoyAgent to source guild configured for target guild
        envoy_spec = (
            AgentBuilder(EnvoyAgent)
            .set_id("envoy")
            .set_name("Envoy")
            .set_description("Standard envoy to target guild")
            .set_properties(EnvoyAgentProps(target_guild=target_guild.id))
            .add_additional_topic("outbound")
            .build_spec()
        )
        source_guild._add_local_agent(envoy_spec)

        probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id("source_probe")
            .set_name("SourceProbe")
            .set_description("Probe in source guild")
            .build_spec()
        )
        source_probe: ProbeAgent = source_guild._add_local_agent(probe_spec)  # type: ignore

        time.sleep(0.5)

        # Send message from source - envoy will forward to its configured target
        source_probe.publish_dict(
            topic="outbound",
            payload={"data": "hello"},
            format="test/json",
        )

        time.sleep(1.0)

        # Verify target probe received the message
        messages = target_probe.get_messages()
        received = [m for m in messages if m.payload.get("data") == "hello"]
        assert len(received) >= 1

        source_guild.shutdown()
        target_guild.shutdown()

    def test_envoy_1_to_1_mapping(self, messaging: MessagingConfig, database, org_id):
        """Test that each EnvoyAgent represents exactly one target guild.

        Setup:
        - Source guild has two EnvoyAgents, each targeting a different guild
        - Each target guild has a GatewayAgent that accepts any source
        """
        # Create source guild
        source_guild = (
            GuildBuilder(guild_name="source_guild", guild_description="Source")
            .set_messaging(messaging.backend_module, messaging.backend_class, messaging.backend_config)
            .bootstrap(database, org_id)
        )

        # Create two target guilds
        target_a = (
            GuildBuilder(guild_name="target_a", guild_description="Target A")
            .set_messaging(messaging.backend_module, messaging.backend_class, messaging.backend_config)
            .bootstrap(database, org_id)
        )

        target_b = (
            GuildBuilder(guild_name="target_b", guild_description="Target B")
            .set_messaging(messaging.backend_module, messaging.backend_class, messaging.backend_config)
            .bootstrap(database, org_id)
        )

        # Add gateways and probes to both targets
        gateway_a_spec = (
            AgentBuilder(GatewayAgent)
            .set_id("gateway")
            .set_name("Gateway")
            .set_description("Gateway")
            .build_spec()
        )
        target_a._add_local_agent(gateway_a_spec)

        gateway_b_spec = (
            AgentBuilder(GatewayAgent)
            .set_id("gateway")
            .set_name("Gateway")
            .set_description("Gateway")
            .build_spec()
        )
        target_b._add_local_agent(gateway_b_spec)

        probe_a_spec = (
            AgentBuilder(ProbeAgent)
            .set_id("probe_a")
            .set_name("ProbeA")
            .set_description("Probe in target A")
            .build_spec()
        )
        probe_a: ProbeAgent = target_a._add_local_agent(probe_a_spec)  # type: ignore

        probe_b_spec = (
            AgentBuilder(ProbeAgent)
            .set_id("probe_b")
            .set_name("ProbeB")
            .set_description("Probe in target B")
            .build_spec()
        )
        probe_b: ProbeAgent = target_b._add_local_agent(probe_b_spec)  # type: ignore

        # Add TWO envoys to source guild - one for each target
        envoy_a_spec = (
            AgentBuilder(EnvoyAgent)
            .set_id("envoy_to_a")
            .set_name("EnvoyToA")
            .set_description("Envoy to target A")
            .set_properties(EnvoyAgentProps(target_guild=target_a.id))
            .add_additional_topic("to_target_a")
            .build_spec()
        )
        source_guild._add_local_agent(envoy_a_spec)

        envoy_b_spec = (
            AgentBuilder(EnvoyAgent)
            .set_id("envoy_to_b")
            .set_name("EnvoyToB")
            .set_description("Envoy to target B")
            .set_properties(EnvoyAgentProps(target_guild=target_b.id))
            .add_additional_topic("to_target_b")
            .build_spec()
        )
        source_guild._add_local_agent(envoy_b_spec)

        probe_spec = AgentBuilder(ProbeAgent).set_id("probe").set_name("Probe").set_description("Probe").build_spec()
        source_probe: ProbeAgent = source_guild._add_local_agent(probe_spec)  # type: ignore

        time.sleep(0.5)

        # Send to target A via envoy_to_a
        source_probe.publish_dict(
            topic="to_target_a",
            payload={"data": "for_a"},
            format="test/json",
        )

        # Send to target B via envoy_to_b
        source_probe.publish_dict(
            topic="to_target_b",
            payload={"data": "for_b"},
            format="test/json",
        )

        time.sleep(1.0)

        # Verify each target received only its message
        a_messages = [m for m in probe_a.get_messages() if m.payload.get("data") == "for_a"]
        b_messages = [m for m in probe_b.get_messages() if m.payload.get("data") == "for_b"]

        # Verify no cross-contamination
        a_wrong = [m for m in probe_a.get_messages() if m.payload.get("data") == "for_b"]
        b_wrong = [m for m in probe_b.get_messages() if m.payload.get("data") == "for_a"]

        assert len(a_messages) >= 1, "Target A should receive message sent via envoy_to_a"
        assert len(b_messages) >= 1, "Target B should receive message sent via envoy_to_b"
        assert len(a_wrong) == 0, "Target A should not receive message for B"
        assert len(b_wrong) == 0, "Target B should not receive message for A"

        source_guild.shutdown()
        target_a.shutdown()
        target_b.shutdown()

    def test_gateway_allowed_source_guilds(self, messaging: MessagingConfig, database, org_id):
        """Test GatewayAgent filters messages from unauthorized guilds.

        Setup:
        - Target guild has a GatewayAgent with allowed_source_guilds filter
        - Two source guilds both have envoys to target, but only one is allowed
        """
        # Create source guilds first
        allowed_source = (
            GuildBuilder(guild_name="allowed_source", guild_description="Allowed")
            .set_messaging(messaging.backend_module, messaging.backend_class, messaging.backend_config)
            .bootstrap(database, org_id)
        )

        blocked_source = (
            GuildBuilder(guild_name="blocked_source", guild_description="Blocked")
            .set_messaging(messaging.backend_module, messaging.backend_class, messaging.backend_config)
            .bootstrap(database, org_id)
        )

        # Create target guild
        target_guild = (
            GuildBuilder(guild_name="target_guild", guild_description="Target")
            .set_messaging(messaging.backend_module, messaging.backend_class, messaging.backend_config)
            .bootstrap(database, org_id)
        )

        # Add gateway that only allows specific source guild
        gateway_spec = (
            AgentBuilder(GatewayAgent)
            .set_id("gateway")
            .set_name("Gateway")
            .set_description("Gateway for allowed source only")
            .set_properties(
                GatewayAgentProps(
                    allowed_source_guilds=[allowed_source.id],
                )
            )
            .build_spec()
        )
        target_guild._add_local_agent(gateway_spec)

        target_probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id("target_probe")
            .set_name("TargetProbe")
            .set_description("Probe")
            .build_spec()
        )
        target_probe: ProbeAgent = target_guild._add_local_agent(target_probe_spec)  # type: ignore

        # Add envoys (configured for target) and probes to both source guilds
        allowed_envoy_spec = (
            AgentBuilder(EnvoyAgent)
            .set_id("envoy")
            .set_name("Envoy")
            .set_description("Envoy to target")
            .set_properties(EnvoyAgentProps(target_guild=target_guild.id))
            .add_additional_topic("outbound")
            .build_spec()
        )
        allowed_source._add_local_agent(allowed_envoy_spec)

        allowed_probe_spec = (
            AgentBuilder(ProbeAgent).set_id("probe").set_name("Probe").set_description("Probe").build_spec()
        )
        allowed_probe: ProbeAgent = allowed_source._add_local_agent(allowed_probe_spec)  # type: ignore

        blocked_envoy_spec = (
            AgentBuilder(EnvoyAgent)
            .set_id("envoy")
            .set_name("Envoy")
            .set_description("Envoy to target")
            .set_properties(EnvoyAgentProps(target_guild=target_guild.id))
            .add_additional_topic("outbound")
            .build_spec()
        )
        blocked_source._add_local_agent(blocked_envoy_spec)

        blocked_probe_spec = (
            AgentBuilder(ProbeAgent).set_id("probe").set_name("Probe").set_description("Probe").build_spec()
        )
        blocked_probe: ProbeAgent = blocked_source._add_local_agent(blocked_probe_spec)  # type: ignore

        time.sleep(0.5)

        # Send from both sources
        allowed_probe.publish_dict(
            topic="outbound",
            payload={"source": "allowed"},
            format="test/json",
        )

        blocked_probe.publish_dict(
            topic="outbound",
            payload={"source": "blocked"},
            format="test/json",
        )

        time.sleep(1.5)

        # Verify only allowed message was forwarded
        messages = target_probe.get_messages()
        allowed_msgs = [m for m in messages if m.payload.get("source") == "allowed"]
        blocked_msgs = [m for m in messages if m.payload.get("source") == "blocked"]

        assert len(allowed_msgs) >= 1, "Message from allowed source should be forwarded"
        assert len(blocked_msgs) == 0, "Message from blocked source should be dropped"

        allowed_source.shutdown()
        blocked_source.shutdown()
        target_guild.shutdown()

    def test_envoy_allowed_target_guilds(self, messaging: MessagingConfig, database, org_id):
        """Test EnvoyAgent filters messages when target guild is not in allowed list.

        Setup:
        - Source guild has two envoys, one to each target
        - One envoy's target is in its allowed list, the other's is not
        """
        # Create source guild first
        source_guild = (
            GuildBuilder(guild_name="source_guild", guild_description="Source")
            .set_messaging(messaging.backend_module, messaging.backend_class, messaging.backend_config)
            .bootstrap(database, org_id)
        )

        # Create target guilds
        allowed_target = (
            GuildBuilder(guild_name="allowed_target", guild_description="Allowed Target")
            .set_messaging(messaging.backend_module, messaging.backend_class, messaging.backend_config)
            .bootstrap(database, org_id)
        )

        blocked_target = (
            GuildBuilder(guild_name="blocked_target", guild_description="Blocked Target")
            .set_messaging(messaging.backend_module, messaging.backend_class, messaging.backend_config)
            .bootstrap(database, org_id)
        )

        # Add gateways and probes to both targets
        allowed_gateway_spec = (
            AgentBuilder(GatewayAgent)
            .set_id("gateway")
            .set_name("Gateway")
            .set_description("Gateway")
            .build_spec()
        )
        allowed_target._add_local_agent(allowed_gateway_spec)

        blocked_gateway_spec = (
            AgentBuilder(GatewayAgent)
            .set_id("gateway")
            .set_name("Gateway")
            .set_description("Gateway")
            .build_spec()
        )
        blocked_target._add_local_agent(blocked_gateway_spec)

        allowed_probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id("allowed_probe")
            .set_name("AllowedProbe")
            .set_description("Probe in allowed target")
            .build_spec()
        )
        allowed_probe: ProbeAgent = allowed_target._add_local_agent(allowed_probe_spec)  # type: ignore

        blocked_probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id("blocked_probe")
            .set_name("BlockedProbe")
            .set_description("Probe in blocked target")
            .build_spec()
        )
        blocked_probe: ProbeAgent = blocked_target._add_local_agent(blocked_probe_spec)  # type: ignore

        # Add envoys to source guild
        # Envoy to allowed target - should work (allowed_target is in allowed list)
        envoy_allowed_spec = (
            AgentBuilder(EnvoyAgent)
            .set_id("envoy_allowed")
            .set_name("EnvoyAllowed")
            .set_description("Envoy to allowed target")
            .set_properties(EnvoyAgentProps(target_guild=allowed_target.id, allowed_target_guilds=[allowed_target.id]))
            .add_additional_topic("to_allowed")
            .build_spec()
        )
        source_guild._add_local_agent(envoy_allowed_spec)

        # Envoy to blocked target - should NOT work (blocked_target is not in allowed list)
        envoy_blocked_spec = (
            AgentBuilder(EnvoyAgent)
            .set_id("envoy_blocked")
            .set_name("EnvoyBlocked")
            .set_description("Envoy to blocked target with restriction")
            .set_properties(
                EnvoyAgentProps(
                    target_guild=blocked_target.id,
                    allowed_target_guilds=[allowed_target.id],  # blocked_target not in list!
                )
            )
            .add_additional_topic("to_blocked")
            .build_spec()
        )
        source_guild._add_local_agent(envoy_blocked_spec)

        probe_spec = AgentBuilder(ProbeAgent).set_id("probe").set_name("Probe").set_description("Probe").build_spec()
        source_probe: ProbeAgent = source_guild._add_local_agent(probe_spec)  # type: ignore

        time.sleep(0.5)

        # Send via both envoys
        source_probe.publish_dict(
            topic="to_allowed",
            payload={"destination": "allowed"},
            format="test/json",
        )

        source_probe.publish_dict(
            topic="to_blocked",
            payload={"destination": "blocked"},
            format="test/json",
        )

        time.sleep(1.5)

        # Verify only allowed target received message
        allowed_msgs = [m for m in allowed_probe.get_messages() if m.payload.get("destination") == "allowed"]
        blocked_msgs = [m for m in blocked_probe.get_messages() if m.payload.get("destination") == "blocked"]

        assert len(allowed_msgs) >= 1, "Message to allowed target should be sent"
        assert len(blocked_msgs) == 0, "Message to blocked target should be dropped"

        source_guild.shutdown()
        allowed_target.shutdown()
        blocked_target.shutdown()

    def test_gateway_input_format_filtering(self, messaging: MessagingConfig, database, org_id):
        """Test GatewayAgent filters by input_formats and output_formats.

        Setup:
        - Gateway configured with specific input_formats (what to accept from source)
        - Messages with matching formats should be forwarded internally
        - Messages with non-matching formats should be dropped
        """
        # Create source and target guilds
        source_guild = (
            GuildBuilder(guild_name="source_guild", guild_description="Source")
            .set_messaging(messaging.backend_module, messaging.backend_class, messaging.backend_config)
            .bootstrap(database, org_id)
        )

        target_guild = (
            GuildBuilder(guild_name="target_guild", guild_description="Target")
            .set_messaging(messaging.backend_module, messaging.backend_class, messaging.backend_config)
            .bootstrap(database, org_id)
        )

        # Gateway that only accepts "allowed/format" messages
        gateway_spec = (
            AgentBuilder(GatewayAgent)
            .set_id("gateway")
            .set_name("Gateway")
            .set_description("Gateway with format filter")
            .set_properties(
                GatewayAgentProps(
                    input_formats=["allowed/format"],
                )
            )
            .build_spec()
        )
        target_guild._add_local_agent(gateway_spec)

        target_probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id("target_probe")
            .set_name("TargetProbe")
            .set_description("Probe in target")
            .build_spec()
        )
        target_probe: ProbeAgent = target_guild._add_local_agent(target_probe_spec)  # type: ignore

        # Envoy in source
        envoy_spec = (
            AgentBuilder(EnvoyAgent)
            .set_id("envoy")
            .set_name("Envoy")
            .set_description("Envoy to target")
            .set_properties(EnvoyAgentProps(target_guild=target_guild.id))
            .add_additional_topic("outbound")
            .build_spec()
        )
        source_guild._add_local_agent(envoy_spec)

        source_probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id("source_probe")
            .set_name("SourceProbe")
            .set_description("Probe in source")
            .build_spec()
        )
        source_probe: ProbeAgent = source_guild._add_local_agent(source_probe_spec)  # type: ignore

        time.sleep(0.5)

        # Send message with allowed format
        source_probe.publish_dict(
            topic="outbound",
            payload={"type": "allowed"},
            format="allowed/format",
        )

        # Send message with blocked format
        source_probe.publish_dict(
            topic="outbound",
            payload={"type": "blocked"},
            format="blocked/format",
        )

        time.sleep(1.5)

        # Verify only allowed format message was forwarded
        messages = target_probe.get_messages()
        allowed_msgs = [m for m in messages if m.payload.get("type") == "allowed"]
        blocked_msgs = [m for m in messages if m.payload.get("type") == "blocked"]

        assert len(allowed_msgs) >= 1, "Message with allowed format should be forwarded"
        assert len(blocked_msgs) == 0, "Message with blocked format should be dropped"

        source_guild.shutdown()
        target_guild.shutdown()

    def test_multi_guild_hop_routing(self, messaging: MessagingConfig, database, org_id):
        """Test multi-guild-hop routing: A -> B -> C -> B -> A.

        This tests the origin_guild_stack mechanism which tracks the chain of guilds
        and routes responses back through the same chain.

        Setup:
        - Guild A (client): Has Envoy to B and Gateway to receive responses
        - Guild B (middle): Has Gateway (receives from A), Envoy to C, and Gateway for responses
        - Guild C (backend): Has Gateway and ResponderAgent that sends responses

        Flow:
        1. A sends request to B (stack becomes ["A"])
        2. B forwards to C (stack becomes ["A", "B"])
        3. C processes and responds (stack still ["A", "B"])
        4. C's Gateway forwards response to B (based on stack top)
        5. B's Gateway receives, pops stack (now ["A"]), forwards to A
        6. A's Gateway receives, pops stack (now []), forwards internally
        """
        # Create Guild A (client)
        guild_a = (
            GuildBuilder(guild_name="guild_a_client", guild_description="Client Guild A")
            .set_messaging(messaging.backend_module, messaging.backend_class, messaging.backend_config)
            .bootstrap(database, org_id)
        )

        # Create Guild B (middle layer)
        guild_b = (
            GuildBuilder(guild_name="guild_b_middle", guild_description="Middle Guild B")
            .set_messaging(messaging.backend_module, messaging.backend_class, messaging.backend_config)
            .bootstrap(database, org_id)
        )

        # Create Guild C (backend)
        guild_c = (
            GuildBuilder(guild_name="guild_c_backend", guild_description="Backend Guild C")
            .set_messaging(messaging.backend_module, messaging.backend_class, messaging.backend_config)
            .bootstrap(database, org_id)
        )

        # --- Guild A setup ---
        # Gateway to receive responses
        gateway_a_spec = (
            AgentBuilder(GatewayAgent)
            .set_id("gateway_a")
            .set_name("GatewayA")
            .set_description("Gateway for Guild A")
            .set_properties(
                GatewayAgentProps(
                    input_formats=["request/json"],  # Accept requests (shouldn't get any)
                    output_formats=["response/json"],  # Forward responses back
                    returned_formats=["response/json"],  # Accept returned responses
                )
            )
            .build_spec()
        )
        guild_a._add_local_agent(gateway_a_spec)

        # Envoy to send to Guild B
        envoy_a_spec = (
            AgentBuilder(EnvoyAgent)
            .set_id("envoy_a")
            .set_name("EnvoyA")
            .set_description("Envoy from A to B")
            .set_properties(
                EnvoyAgentProps(
                    target_guild=guild_b.id,
                    formats_to_forward=["request/json"],
                )
            )
            .add_additional_topic("outbound")
            .build_spec()
        )
        guild_a._add_local_agent(envoy_a_spec)

        # Probe in A to send requests and observe responses
        probe_a_spec = (
            AgentBuilder(ProbeAgent)
            .set_id("probe_a")
            .set_name("ProbeA")
            .set_description("Probe in Guild A")
            .build_spec()
        )
        probe_a: ProbeAgent = guild_a._add_local_agent(probe_a_spec)  # type: ignore

        # --- Guild B setup ---
        # Gateway to receive from A and handle responses from C
        gateway_b_spec = (
            AgentBuilder(GatewayAgent)
            .set_id("gateway_b")
            .set_name("GatewayB")
            .set_description("Gateway for Guild B")
            .set_properties(
                GatewayAgentProps(
                    input_formats=["request/json"],  # Accept requests from A
                    output_formats=["response/json"],  # Forward responses back to A
                    returned_formats=["response/json"],  # Accept returned responses from C
                )
            )
            .build_spec()
        )
        guild_b._add_local_agent(gateway_b_spec)

        # Envoy to forward to Guild C
        envoy_b_spec = (
            AgentBuilder(EnvoyAgent)
            .set_id("envoy_b")
            .set_name("EnvoyB")
            .set_description("Envoy from B to C")
            .set_properties(
                EnvoyAgentProps(
                    target_guild=guild_c.id,
                    formats_to_forward=["request/json"],
                )
            )
            .build_spec()
        )
        guild_b._add_local_agent(envoy_b_spec)

        # Probe in B to observe messages
        probe_b_spec = (
            AgentBuilder(ProbeAgent)
            .set_id("probe_b")
            .set_name("ProbeB")
            .set_description("Probe in Guild B")
            .build_spec()
        )
        probe_b: ProbeAgent = guild_b._add_local_agent(probe_b_spec)  # type: ignore

        # --- Guild C setup ---
        # Gateway to receive from B and send responses back
        gateway_c_spec = (
            AgentBuilder(GatewayAgent)
            .set_id("gateway_c")
            .set_name("GatewayC")
            .set_description("Gateway for Guild C")
            .set_properties(
                GatewayAgentProps(
                    input_formats=["request/json"],  # Accept requests from B
                    output_formats=["response/json"],  # Forward responses back to B
                )
            )
            .build_spec()
        )
        guild_c._add_local_agent(gateway_c_spec)

        # Responder that processes requests and sends responses
        responder_spec = (
            AgentBuilder(ResponderAgent)
            .set_id("responder")
            .set_name("Responder")
            .set_description("Processes requests and sends responses")
            .build_spec()
        )
        responder: ResponderAgent = guild_c._add_local_agent(responder_spec)  # type: ignore

        time.sleep(1.0)

        # Send request from Guild A
        probe_a.publish_dict(
            topic="outbound",
            payload={"request_id": "req_001", "data": "hello_world"},
            format="request/json",
        )

        # Wait for the full round-trip: A -> B -> C -> B -> A
        time.sleep(3.0)

        # Verify C's responder received and processed the request
        assert len(responder.received_requests) >= 1, "Responder in C should receive the request"
        assert responder.received_requests[0].get("request_id") == "req_001"

        # Verify B saw BOTH the request AND the response (intermediate processing)
        b_messages = probe_b.get_messages()
        b_requests = [m for m in b_messages if m.format == "request/json"]
        b_responses = [m for m in b_messages if m.format == "response/json"]

        assert len(b_requests) >= 1, "Guild B should see the request passing through"
        assert len(b_responses) >= 1, (
            "Guild B should see the response passing through. "
            "This verifies intermediate guilds can process responses."
        )

        # Verify the response B saw has stack=["A"] (B was popped)
        assert b_responses[0].origin_guild_stack == [guild_a.id], (
            "Response at B should have stack with only A (B was popped)"
        )

        # Verify A received the response (the key test for multi-hop)
        a_messages = probe_a.get_messages()
        responses = [m for m in a_messages if m.payload.get("response_to") == "req_001"]

        assert len(responses) >= 1, (
            "Guild A should receive response routed back through B. "
            "This verifies the origin_guild_stack routing works for multi-hop."
        )
        assert responses[0].payload.get("result") == "processed_hello_world"

        # Verify the response has an empty origin_guild_stack (round-trip complete)
        assert responses[0].origin_guild_stack == [], (
            "Response should have empty origin_guild_stack after completing round-trip"
        )

        guild_a.shutdown()
        guild_b.shutdown()
        guild_c.shutdown()
