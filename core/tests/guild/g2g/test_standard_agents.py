"""
Tests for standard Gateway and Envoy agents.

These tests verify the standard GatewayAgent and EnvoyAgent implementations.

GatewayAgent: Server-like agent that accepts messages from external guilds.
- Receives messages from external guilds
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
from rustic_ai.core.messaging import MessagingConfig
from rustic_ai.core.utils import JsonDict


class ResponderAgent(Agent):
    """Internal agent that processes requests and sends responses."""

    def __init__(self):
        self.received_requests = []

    @agent.processor(JsonDict, predicate=lambda self, msg: msg.format == "MyRequest")
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
            format="MyResponse",
        )


class MiddleGuildRequestProcessor(Agent):
    """Processor in middle guild that handles incoming requests and forwards them."""

    def __init__(self):
        self.processed_requests = []

    @agent.processor(JsonDict, predicate=lambda self, msg: msg.format == "MyRequest")
    def handle_request(self, ctx: agent.ProcessContext[JsonDict]) -> None:
        """Process incoming request and forward to next guild."""
        self.processed_requests.append(ctx.payload)
        # Forward the request - EnvoyB will pick this up and send to Guild C
        ctx.send_dict(
            payload=ctx.payload,
            format="MyRequest",
        )


class MiddleGuildResponseProcessor(Agent):
    """Processor in middle guild that handles returned responses and forwards them."""

    def __init__(self):
        self.processed_responses = []

    @agent.processor(JsonDict, predicate=lambda self, msg: msg.format == "MyResponse")
    def handle_response(self, ctx: agent.ProcessContext[JsonDict]) -> None:
        """Process returned response and forward back to origin guild."""
        self.processed_responses.append(ctx.payload)
        # Forward the response - GatewayB will pick this up and send back to Guild A
        ctx.send_dict(
            payload=ctx.payload,
            format="MyResponse",
        )


class SagaResponderAgent(Agent):
    """Agent that processes requests with saga state and sends responses.

    Used for testing session_state preservation across guild boundaries.
    """

    def __init__(self):
        self.received_messages = []

    @agent.processor(JsonDict, predicate=lambda self, msg: msg.format == "MyStateRequest")
    def handle_request(self, ctx: agent.ProcessContext[JsonDict]) -> None:
        """Process request and send response."""
        self.received_messages.append(ctx.message)
        ctx.send_dict(
            payload={
                "response_to": ctx.payload.get("request_id"),
                "result": "success",
            },
            format="MyStateResponse",
        )


class SagaInitiatorAgent(Agent):
    """Agent that sends requests with session_state and captures responses.

    Used for testing session_state preservation across guild boundaries.
    """

    def __init__(self):
        self.responses_with_session_state = []

    @agent.processor(JsonDict, predicate=lambda self, msg: msg.format == "trigger")
    def initiate_request(self, ctx: agent.ProcessContext[JsonDict]) -> None:
        """Send a request with session_state."""
        # Set session state before sending
        session_state = {
            "user_context": "important_data",
            "step": 1,
            "correlation_id": ctx.payload.get("correlation_id"),
        }
        ctx.send_dict(
            payload={
                "request_id": ctx.payload.get("correlation_id"),
                "action": "process",
            },
            format="MyStateRequest",
            topics=["outbound"],
            session_state=session_state,
        )

    @agent.processor(JsonDict, predicate=lambda self, msg: msg.format == "MyStateResponse")
    def handle_response(self, ctx: agent.ProcessContext[JsonDict]) -> None:
        """Capture response with session_state."""
        self.responses_with_session_state.append(
            {
                "payload": ctx.payload,
                "session_state": ctx.message.session_state,
            }
        )


class TestStandardAgents:
    """Test standard Gateway and Envoy agent implementations."""

    @pytest.fixture(scope="function")
    def messaging(self, request) -> MessagingConfig:
        return MessagingConfig(
            backend_module="rustic_ai.core.messaging.backend",
            backend_class="InMemoryMessagingBackend",
            backend_config={},
        )

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
            .set_properties(
                GatewayAgentProps(
                    input_formats=["*"],
                    output_formats=["*"],
                    returned_formats=["*"],
                )
            )
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
            .set_properties(
                EnvoyAgentProps(
                    target_guild=target_guild.id,
                    formats_to_forward=["*"],
                )
            )
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
            format="TestMessage",
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
            .set_properties(
                GatewayAgentProps(
                    input_formats=["*"],
                    output_formats=["*"],
                    returned_formats=["*"],
                )
            )
            .build_spec()
        )
        target_a._add_local_agent(gateway_a_spec)

        gateway_b_spec = (
            AgentBuilder(GatewayAgent)
            .set_id("gateway")
            .set_name("Gateway")
            .set_description("Gateway")
            .set_properties(
                GatewayAgentProps(
                    input_formats=["*"],
                    output_formats=["*"],
                    returned_formats=["*"],
                )
            )
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
            .set_properties(
                EnvoyAgentProps(
                    target_guild=target_a.id,
                    formats_to_forward=["*"],
                )
            )
            .add_additional_topic("to_target_a")
            .build_spec()
        )
        source_guild._add_local_agent(envoy_a_spec)

        envoy_b_spec = (
            AgentBuilder(EnvoyAgent)
            .set_id("envoy_to_b")
            .set_name("EnvoyToB")
            .set_description("Envoy to target B")
            .set_properties(
                EnvoyAgentProps(
                    target_guild=target_b.id,
                    formats_to_forward=["*"],
                )
            )
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
            format="TestMessage",
        )

        # Send to target B via envoy_to_b
        source_probe.publish_dict(
            topic="to_target_b",
            payload={"data": "for_b"},
            format="TestMessage",
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
                    input_formats=["AllowedMessage"],
                    output_formats=["*"],
                    returned_formats=["*"],
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
            .set_properties(
                EnvoyAgentProps(
                    target_guild=target_guild.id,
                    formats_to_forward=["*"],
                )
            )
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
            format="AllowedMessage",
        )

        # Send message with blocked format
        source_probe.publish_dict(
            topic="outbound",
            payload={"type": "blocked"},
            format="BlockedMessage",
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
        - Guild B (middle): Has Gateway, RequestProcessor, ResponseProcessor, and Envoy to C
        - Guild C (backend): Has Gateway and ResponderAgent that sends responses

        Flow:
        1. Probe sends MyRequest in Guild A
        2. EnvoyA forwards to Guild B (stack becomes ["A"])
        3. GatewayB receives and forwards internally
        4. RequestProcessorB processes and sends MyRequest
        5. EnvoyB forwards to Guild C (stack becomes ["A", "B"])
        6. GatewayC receives and forwards internally
        7. ResponderC processes and sends MyResponse (stack still ["A", "B"])
        8. GatewayC forwards response to B (based on stack top)
        9. GatewayB receives returned response, pops stack (now ["A"]), forwards internally
        10. ResponseProcessorB processes and sends MyResponse
        11. GatewayB forwards response to A (based on stack top)
        12. GatewayA receives returned response, pops stack (now []), forwards internally
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
                    input_formats=["MyRequest"],  # Accept requests (shouldn't get any)
                    output_formats=["MyResponse"],  # Forward responses back
                    returned_formats=["MyResponse"],  # Accept returned responses
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
                    formats_to_forward=["MyRequest"],
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
                    input_formats=["MyRequest"],  # Accept requests from A
                    output_formats=["MyResponse"],  # Forward responses back to A
                    returned_formats=["MyResponse"],  # Accept returned responses from C
                )
            )
            .build_spec()
        )
        guild_b._add_local_agent(gateway_b_spec)

        # Processor to handle incoming requests and forward to C
        request_processor_b_spec = (
            AgentBuilder(MiddleGuildRequestProcessor)
            .set_id("request_processor_b")
            .set_name("RequestProcessorB")
            .set_description("Processes requests in Guild B and forwards to C")
            .build_spec()
        )
        guild_b._add_local_agent(request_processor_b_spec)  # type: ignore

        # Processor to handle returned responses and forward to A
        response_processor_b_spec = (
            AgentBuilder(MiddleGuildResponseProcessor)
            .set_id("response_processor_b")
            .set_name("ResponseProcessorB")
            .set_description("Processes responses in Guild B and forwards to A")
            .build_spec()
        )
        guild_b._add_local_agent(response_processor_b_spec)  # type: ignore

        # Envoy to forward to Guild C
        envoy_b_spec = (
            AgentBuilder(EnvoyAgent)
            .set_id("envoy_b")
            .set_name("EnvoyB")
            .set_description("Envoy from B to C")
            .set_properties(
                EnvoyAgentProps(
                    target_guild=guild_c.id,
                    formats_to_forward=["MyRequest"],
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
                    input_formats=["MyRequest"],  # Accept requests from B
                    output_formats=["MyResponse"],  # Forward responses back to B
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
            format="MyRequest",
        )

        # Wait for the full round-trip: A -> B -> C -> B -> A
        time.sleep(3.0)

        # Verify C's responder received and processed the request
        assert len(responder.received_requests) >= 1, "Responder in C should receive the request"
        assert responder.received_requests[0].get("request_id") == "req_001"

        # Verify B saw BOTH the request AND the response (intermediate processing)
        b_messages = probe_b.get_messages()
        b_requests = [m for m in b_messages if m.format == "MyRequest"]
        b_responses = [m for m in b_messages if m.format == "MyResponse"]

        assert len(b_requests) >= 1, "Guild B should see the request passing through"
        assert len(b_responses) >= 1, (
            "Guild B should see the response passing through. "
            "This verifies intermediate guilds can process responses."
        )

        # Verify the response B saw has stack=[Entry(A)] (B was popped)
        assert (
            len(b_responses[0].origin_guild_stack) == 1
        ), "Response at B should have stack with only A's entry (B was popped)"
        assert (
            b_responses[0].origin_guild_stack[0].guild_id == guild_a.id
        ), "Response at B should have stack with only A (B was popped)"

        # Verify A received the response (the key test for multi-hop)
        a_messages = probe_a.get_messages()
        responses = [m for m in a_messages if m.payload.get("response_to") == "req_001"]

        assert len(responses) >= 1, (
            "Guild A should receive response routed back through B. "
            "This verifies the origin_guild_stack routing works for multi-hop."
        )
        assert responses[0].payload.get("result") == "processed_hello_world"

        # Verify the response has an empty origin_guild_stack (round-trip complete)
        assert (
            responses[0].origin_guild_stack == []
        ), "Response should have empty origin_guild_stack after completing round-trip"

        guild_a.shutdown()
        guild_b.shutdown()
        guild_c.shutdown()

    def test_saga_session_state_preservation(self, messaging: MessagingConfig, database, org_id):
        """Test that session_state is preserved across guild boundaries via saga pattern.

        When a message with session_state is forwarded to another guild:
        1. EnvoyAgent saves session_state to guild_state with a saga_id
        2. The saga_id is recorded in the GuildStackEntry
        3. When the response returns, GatewayAgent restores session_state from guild_state
        4. The restored session_state is available for continuation processing

        Setup:
        - Source guild sends a request WITH session_state
        - Target guild has a responder that processes and responds
        - Source guild verifies session_state is restored in the response
        """
        from rustic_ai.core.messaging import GuildStackEntry

        # Create source guild
        source_guild = (
            GuildBuilder(guild_name="source_guild", guild_description="Source with session state")
            .set_messaging(messaging.backend_module, messaging.backend_class, messaging.backend_config)
            .bootstrap(database, org_id)
        )

        # Create target guild
        target_guild = (
            GuildBuilder(guild_name="target_guild", guild_description="Target for session state test")
            .set_messaging(messaging.backend_module, messaging.backend_class, messaging.backend_config)
            .bootstrap(database, org_id)
        )

        # Configure target guild with gateway
        gateway_spec = (
            AgentBuilder(GatewayAgent)
            .set_id("gateway")
            .set_name("Gateway")
            .set_description("Gateway for target guild")
            .set_properties(
                GatewayAgentProps(
                    input_formats=["MyStateRequest"],
                    output_formats=["MyStateResponse"],
                    returned_formats=["MyStateResponse"],
                )
            )
            .build_spec()
        )
        target_guild._add_local_agent(gateway_spec)

        # Add responder to target guild
        responder_spec = (
            AgentBuilder(SagaResponderAgent)
            .set_id("responder")
            .set_name("SagaResponder")
            .set_description("Responder in target guild")
            .build_spec()
        )
        responder: SagaResponderAgent = target_guild._add_local_agent(responder_spec)  # type: ignore

        # Configure source guild with gateway for receiving responses
        source_gateway_spec = (
            AgentBuilder(GatewayAgent)
            .set_id("gateway")
            .set_name("Gateway")
            .set_description("Gateway for source guild")
            .set_properties(
                GatewayAgentProps(
                    input_formats=["*"],
                    output_formats=["*"],
                    returned_formats=["MyStateResponse"],
                )
            )
            .build_spec()
        )
        source_guild._add_local_agent(source_gateway_spec)

        # Add envoy to source guild for sending requests
        envoy_spec = (
            AgentBuilder(EnvoyAgent)
            .set_id("envoy")
            .set_name("EnvoyToTarget")
            .set_description("Envoy to target guild")
            .set_properties(
                EnvoyAgentProps(
                    target_guild=target_guild.id,
                    formats_to_forward=["MyStateRequest"],
                )
            )
            .add_additional_topic("outbound")
            .build_spec()
        )
        source_guild._add_local_agent(envoy_spec)

        # Add initiator to source guild to handle response
        initiator_spec = (
            AgentBuilder(SagaInitiatorAgent)
            .set_id("initiator")
            .set_name("SagaInitiator")
            .set_description("Initiator in source guild")
            .build_spec()
        )
        initiator: SagaInitiatorAgent = source_guild._add_local_agent(initiator_spec)  # type: ignore

        # Create probe to send the request directly (instead of triggering initiator)
        probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id("probe")
            .set_name("Probe")
            .set_description("Probe in source guild")
            .build_spec()
        )
        probe: ProbeAgent = source_guild._add_local_agent(probe_spec)  # type: ignore

        # Allow agents to start
        time.sleep(1.0)

        # Send request directly from probe with session_state
        # The envoy will forward this to the target guild
        probe.publish_dict(
            topic="outbound",
            payload={"request_id": "saga_test_001", "action": "process"},
            format="MyStateRequest",
            session_state={
                "user_context": "important_data",
                "step": 1,
                "correlation_id": "saga_test_001",
            },
        )

        # Wait for the round-trip (longer wait time)
        time.sleep(3.0)

        # Verify the responder in target guild received the request
        assert len(responder.received_messages) >= 1, "Target guild responder should receive request"
        received_msg = responder.received_messages[0]

        # Verify the session_state was NOT passed to the target guild (security)
        # session_state should be None or empty dict
        assert (
            not received_msg.session_state
        ), "Session state should NOT be passed across guild boundaries in the request"

        # Verify the origin_guild_stack has a GuildStackEntry with saga_id
        assert len(received_msg.origin_guild_stack) == 1, "Should have one entry in origin_guild_stack"
        stack_entry = received_msg.origin_guild_stack[0]
        assert isinstance(stack_entry, GuildStackEntry), "Stack entry should be GuildStackEntry"
        assert stack_entry.guild_id == source_guild.id, "Stack entry should have source guild ID"
        assert stack_entry.saga_id is not None, "Stack entry should have saga_id for session state preservation"

        # Verify the initiator received the response with session_state restored
        assert (
            len(initiator.responses_with_session_state) >= 1
        ), "Initiator should receive response with restored session_state"
        response_data = initiator.responses_with_session_state[0]

        # Verify payload
        assert response_data["payload"]["response_to"] == "saga_test_001"
        assert response_data["payload"]["result"] == "success"

        # Verify session_state was restored!
        restored_session_state = response_data["session_state"]
        assert restored_session_state is not None, "Session state should be restored when response returns"
        assert (
            restored_session_state.get("user_context") == "important_data"
        ), "Restored session_state should contain original user_context"
        assert restored_session_state.get("step") == 1, "Restored session_state should contain original step"
        assert (
            restored_session_state.get("correlation_id") == "saga_test_001"
        ), "Restored session_state should contain original correlation_id"

        source_guild.shutdown()
        target_guild.shutdown()
