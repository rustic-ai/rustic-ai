"""
Integration tests for VendingBench G2G communication.

Tests the communication between a player guild and the VendingBench guild
using Guild-to-Guild (G2G) messaging.
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
from rustic_ai.showcase.vending_bench.messages import (
    ActionType,
    AgentActionRequest,
    SimulationControlCommand,
    SimulationControlRequest,
)


class VendingBenchResponderAgent(Agent):
    """
    Simple agent that handles VendingBench requests.

    This simulates the VendingBench guild's behavior for testing G2G.
    """

    def __init__(self):
        self.received_requests = []

    @agent.processor(
        JsonDict,
        predicate=lambda self, msg: msg.format
        == "rustic_ai.showcase.vending_bench.messages.SimulationControlRequest",
    )
    def handle_control_request(self, ctx: agent.ProcessContext[JsonDict]) -> None:
        """Handle simulation control requests."""
        self.received_requests.append(ctx.payload)

        # Parse the request
        command = ctx.payload.get("command", "get_status")

        # Send response
        ctx.send_dict(
            payload={
                "request_id": ctx.payload.get("request_id", "test"),
                "command": command,
                "success": True,
                "message": f"Simulation {command} executed successfully",
                "simulation_status": "running" if command == "start" else "completed",
            },
            format="rustic_ai.showcase.vending_bench.messages.SimulationControlResponse",
        )

    @agent.processor(
        JsonDict,
        predicate=lambda self, msg: msg.format
        == "rustic_ai.showcase.vending_bench.messages.AgentActionRequest",
    )
    def handle_action_request(self, ctx: agent.ProcessContext[JsonDict]) -> None:
        """Handle agent action requests."""
        self.received_requests.append(ctx.payload)

        action_type = ctx.payload.get("action_type", "check_inventory")

        # Send response
        ctx.send_dict(
            payload={
                "request_id": ctx.payload.get("request_id", "test"),
                "action_type": action_type,
                "success": True,
                "response": {"inventory": {"chips": 20, "soda": 30}},
                "simulation_time": {
                    "current_day": 1,
                    "current_time_minutes": 0,
                    "is_daytime": True,
                    "weather": "sunny",
                    "day_of_week": 0,
                },
            },
            format="rustic_ai.showcase.vending_bench.messages.AgentActionResponse",
        )


class PlayerResponseAgent(Agent):
    """
    Agent that captures responses from VendingBench.
    """

    def __init__(self):
        self.responses_received = []

    @agent.processor(
        JsonDict,
        predicate=lambda self, msg: msg.format
        == "rustic_ai.showcase.vending_bench.messages.SimulationControlResponse",
    )
    def handle_control_response(self, ctx: agent.ProcessContext[JsonDict]) -> None:
        """Handle simulation control responses."""
        self.responses_received.append(ctx.payload)

    @agent.processor(
        JsonDict,
        predicate=lambda self, msg: msg.format
        == "rustic_ai.showcase.vending_bench.messages.AgentActionResponse",
    )
    def handle_action_response(self, ctx: agent.ProcessContext[JsonDict]) -> None:
        """Handle action responses."""
        self.responses_received.append(ctx.payload)


class TestVendingBenchG2G:
    """Tests for VendingBench G2G integration."""

    @pytest.fixture(scope="function")
    def messaging(self) -> MessagingConfig:
        return MessagingConfig(
            backend_module="rustic_ai.core.messaging.backend",
            backend_class="InMemoryMessagingBackend",
            backend_config={},
        )

    def test_player_guild_sends_to_vending_bench(self, messaging: MessagingConfig, database, org_id):
        """Test that player guild can send requests to VendingBench guild via G2G."""
        # Create VendingBench guild (server)
        vending_bench_guild = (
            GuildBuilder(guild_name="vending_bench", guild_description="VendingBench Simulation")
            .set_messaging(messaging.backend_module, messaging.backend_class, messaging.backend_config)
            .bootstrap(database, org_id)
        )

        # Add Gateway to VendingBench guild
        gateway_spec = (
            AgentBuilder(GatewayAgent)
            .set_id("gateway")
            .set_name("VendingBenchGateway")
            .set_description("Gateway for VendingBench")
            .set_properties(
                GatewayAgentProps(
                    input_formats=[
                        "rustic_ai.showcase.vending_bench.messages.SimulationControlRequest",
                        "rustic_ai.showcase.vending_bench.messages.AgentActionRequest",
                    ],
                    output_formats=[
                        "rustic_ai.showcase.vending_bench.messages.SimulationControlResponse",
                        "rustic_ai.showcase.vending_bench.messages.AgentActionResponse",
                    ],
                    returned_formats=["*"],
                )
            )
            .build_spec()
        )
        vending_bench_guild._add_local_agent(gateway_spec)

        # Add responder to handle requests
        responder_spec = (
            AgentBuilder(VendingBenchResponderAgent)
            .set_id("responder")
            .set_name("VendingBenchResponder")
            .set_description("Handles VendingBench requests")
            .build_spec()
        )
        responder: VendingBenchResponderAgent = vending_bench_guild._add_local_agent(responder_spec)

        # Create Player guild (client)
        player_guild = (
            GuildBuilder(guild_name="player_guild", guild_description="VendingBench Player")
            .set_messaging(messaging.backend_module, messaging.backend_class, messaging.backend_config)
            .bootstrap(database, org_id)
        )

        # Add Gateway to Player guild for receiving responses
        player_gateway_spec = (
            AgentBuilder(GatewayAgent)
            .set_id("gateway")
            .set_name("PlayerGateway")
            .set_description("Gateway for Player")
            .set_properties(
                GatewayAgentProps(
                    input_formats=["*"],
                    output_formats=["*"],
                    returned_formats=[
                        "rustic_ai.showcase.vending_bench.messages.SimulationControlResponse",
                        "rustic_ai.showcase.vending_bench.messages.AgentActionResponse",
                    ],
                )
            )
            .build_spec()
        )
        player_guild._add_local_agent(player_gateway_spec)

        # Add Envoy to send to VendingBench
        envoy_spec = (
            AgentBuilder(EnvoyAgent)
            .set_id("envoy_to_vending_bench")
            .set_name("EnvoyToVendingBench")
            .set_description("Envoy to VendingBench guild")
            .set_properties(
                EnvoyAgentProps(
                    target_guild=vending_bench_guild.id,
                    formats_to_forward=[
                        "rustic_ai.showcase.vending_bench.messages.SimulationControlRequest",
                        "rustic_ai.showcase.vending_bench.messages.AgentActionRequest",
                    ],
                )
            )
            .add_additional_topic("to_vending_bench")
            .build_spec()
        )
        player_guild._add_local_agent(envoy_spec)

        # Add player response agent
        player_agent_spec = (
            AgentBuilder(PlayerResponseAgent)
            .set_id("player_agent")
            .set_name("PlayerAgent")
            .set_description("Player that receives VendingBench responses")
            .build_spec()
        )
        player_agent: PlayerResponseAgent = player_guild._add_local_agent(player_agent_spec)

        # Add probe to send requests
        probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id("probe")
            .set_name("Probe")
            .set_description("Test probe")
            .build_spec()
        )
        probe: ProbeAgent = player_guild._add_local_agent(probe_spec)

        # Allow agents to start
        time.sleep(0.5)

        # Send a start simulation request via the outbound topic (picked up by Envoy)
        request = SimulationControlRequest(command=SimulationControlCommand.START)
        probe.publish_dict(
            topic="to_vending_bench",
            payload=request.model_dump(),
            format="rustic_ai.showcase.vending_bench.messages.SimulationControlRequest",
        )

        # Wait for the request to be processed
        time.sleep(2.0)

        # Verify VendingBench received the request
        assert len(responder.received_requests) >= 1, "VendingBench should receive the request"
        assert responder.received_requests[0].get("command") == "start"

        # Verify Player received the response
        assert len(player_agent.responses_received) >= 1, "Player should receive response"
        assert player_agent.responses_received[0].get("success") is True
        assert player_agent.responses_received[0].get("simulation_status") == "running"

        # Cleanup
        player_guild.shutdown()
        vending_bench_guild.shutdown()

    def test_round_trip_action_request(self, messaging: MessagingConfig, database, org_id):
        """Test a complete round-trip action request via G2G."""
        # Create VendingBench guild
        vending_bench_guild = (
            GuildBuilder(guild_name="vending_bench_2", guild_description="VendingBench")
            .set_messaging(messaging.backend_module, messaging.backend_class, messaging.backend_config)
            .bootstrap(database, org_id)
        )

        # Gateway for VendingBench
        vb_gateway_spec = (
            AgentBuilder(GatewayAgent)
            .set_id("gateway")
            .set_name("Gateway")
            .set_description("VendingBench Gateway")
            .set_properties(
                GatewayAgentProps(
                    input_formats=["*"],
                    output_formats=["*"],
                    returned_formats=["*"],
                )
            )
            .build_spec()
        )
        vending_bench_guild._add_local_agent(vb_gateway_spec)

        # Responder
        responder_spec = (
            AgentBuilder(VendingBenchResponderAgent)
            .set_id("responder")
            .set_name("Responder")
            .set_description("VendingBench Responder")
            .build_spec()
        )
        vending_bench_guild._add_local_agent(responder_spec)

        # Create Player guild
        player_guild = (
            GuildBuilder(guild_name="player_guild_2", guild_description="Player")
            .set_messaging(messaging.backend_module, messaging.backend_class, messaging.backend_config)
            .bootstrap(database, org_id)
        )

        # Gateway for Player
        player_gateway_spec = (
            AgentBuilder(GatewayAgent)
            .set_id("gateway")
            .set_name("Gateway")
            .set_description("Player Gateway")
            .set_properties(
                GatewayAgentProps(
                    input_formats=["*"],
                    output_formats=["*"],
                    returned_formats=["*"],
                )
            )
            .build_spec()
        )
        player_guild._add_local_agent(player_gateway_spec)

        # Envoy to VendingBench
        envoy_spec = (
            AgentBuilder(EnvoyAgent)
            .set_id("envoy")
            .set_name("Envoy")
            .set_description("Envoy to VendingBench")
            .set_properties(
                EnvoyAgentProps(
                    target_guild=vending_bench_guild.id,
                    formats_to_forward=["*"],
                )
            )
            .add_additional_topic("outbound")
            .build_spec()
        )
        player_guild._add_local_agent(envoy_spec)

        # Probe
        probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id("probe")
            .set_name("Probe")
            .set_description("Test probe")
            .build_spec()
        )
        probe: ProbeAgent = player_guild._add_local_agent(probe_spec)

        time.sleep(0.5)

        # Send an action request
        request = AgentActionRequest(
            action_type=ActionType.CHECK_INVENTORY,
            parameters={},
        )
        probe.publish_dict(
            topic="outbound",
            payload=request.model_dump(),
            format="rustic_ai.showcase.vending_bench.messages.AgentActionRequest",
        )

        time.sleep(2.0)

        # Check that the probe received the response
        messages = probe.get_messages()
        responses = [
            m
            for m in messages
            if m.format == "rustic_ai.showcase.vending_bench.messages.AgentActionResponse"
        ]

        assert len(responses) >= 1, "Should receive action response"
        assert responses[0].payload.get("success") is True
        assert responses[0].payload.get("action_type") == "check_inventory"
        assert "inventory" in responses[0].payload.get("response", {})

        # Cleanup
        player_guild.shutdown()
        vending_bench_guild.shutdown()
