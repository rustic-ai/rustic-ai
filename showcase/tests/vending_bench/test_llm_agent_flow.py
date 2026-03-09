"""
Test for the LLM Agent flow in VendingBench Player Guild.

This test traces the flow from:
1. Simulation starts
2. LLM receives SimulationControlResponse (transformed to ChatCompletionRequest)
3. LLM calls a tool (e.g., search_suppliers)
4. Tool response comes back (AgentActionResponse)
5. LLM should receive the response and call another tool

The goal is to identify where the flow breaks after the first tool call.
"""

import time
from typing import List
from unittest.mock import MagicMock

import pytest

from rustic_ai.core.agents.testutils import ProbeAgent
from rustic_ai.core.guild import Agent, agent
from rustic_ai.core.guild.agent import ProcessContext
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    AssistantMessage,
    ChatCompletionMessageToolCall,
    ChatCompletionRequest,
    ChatCompletionResponse,
    Choice,
    FunctionCall,
)
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.guild.g2g.gateway_agent import GatewayAgent
from rustic_ai.core.messaging import MessagingConfig
from rustic_ai.core.messaging.core.message import (
    RoutingDestination,
    RoutingRule,
    RoutingSlip,
)
from rustic_ai.llm_agent.tools.tools_manager_plugin import ToolsManagerPlugin
from rustic_ai.showcase.vending_bench.messages import (
    ActionType,
    AgentActionResponse,
    SimulationTime,
    WeatherType,
)
from rustic_ai.showcase.vending_bench.player_toolset import (
    VendingBenchToolspecsProvider,
)
from rustic_ai.showcase.vending_bench.supplier_messages import SupplierSearchRequest


class MockLLMAgent(Agent):
    """
    A mock LLM agent that simulates the LLMAgent behavior.
    Records all received ChatCompletionRequests and returns predefined tool calls.
    """

    def __init__(self):
        self.received_requests: List[ChatCompletionRequest] = []
        self.call_count = 0
        self.tool_calls_to_return: List[List[ChatCompletionMessageToolCall]] = []

    def set_tool_calls(self, tool_calls_sequence: List[List[ChatCompletionMessageToolCall]]):
        """Set the sequence of tool calls to return for each LLM invocation."""
        self.tool_calls_to_return = tool_calls_sequence

    @agent.processor(ChatCompletionRequest)
    def handle_chat_request(self, ctx: ProcessContext[ChatCompletionRequest]):
        """Handle incoming ChatCompletionRequest and return mock response."""
        request = ctx.payload
        self.received_requests.append(request)

        # Log what we received
        print(f"\n[MockLLMAgent] Received ChatCompletionRequest #{self.call_count + 1}")
        for msg in request.messages or []:
            print(f"  - {msg.role}: {str(msg.content)[:100]}...")

        # Determine what to return
        if self.call_count < len(self.tool_calls_to_return):
            tool_calls = self.tool_calls_to_return[self.call_count]
        else:
            # No more tool calls - return text response
            tool_calls = None

        self.call_count += 1

        if tool_calls:
            # Return response with tool calls
            response = ChatCompletionResponse(
                id=f"mock-{self.call_count}",
                created=int(time.time()),
                choices=[
                    Choice(
                        index=0,
                        message=AssistantMessage(
                            role="assistant",
                            content=None,
                            tool_calls=tool_calls,
                        ),
                        finish_reason="tool_calls",
                    )
                ],
                model="mock-model",
            )
        else:
            # Return text response
            response = ChatCompletionResponse(
                id=f"mock-{self.call_count}",
                created=int(time.time()),
                choices=[
                    Choice(
                        index=0,
                        message=AssistantMessage(
                            role="assistant",
                            content="I've completed my analysis.",
                        ),
                        finish_reason="stop",
                    )
                ],
                model="mock-model",
            )

        print(f"[MockLLMAgent] Returning response with tool_calls={tool_calls is not None}")
        ctx.send(response)


class TestLLMAgentFlow:
    """Tests for the LLM agent flow in VendingBench."""

    @pytest.fixture
    def messaging(self) -> MessagingConfig:
        return MessagingConfig(
            backend_module="rustic_ai.core.messaging.backend",
            backend_class="InMemoryMessagingBackend",
            backend_config={},
        )

    def test_chat_completion_request_routing(self, messaging, org_id):
        """
        Test that ChatCompletionRequest is properly routed to the LLM agent.

        This simulates the flow after an AgentActionResponse comes back from VendingBench.
        """
        # Create a simple guild with MockLLMAgent
        guild = (
            GuildBuilder(guild_name="test_player_guild", guild_description="Test Player Guild")
            .set_messaging(messaging.backend_module, messaging.backend_class, messaging.backend_config)
            .launch(org_id)
        )

        # Add MockLLMAgent that listens to PLAYER_INPUT
        mock_llm_spec = (
            AgentBuilder(MockLLMAgent)
            .set_id("mock_llm")
            .set_name("MockLLM")
            .set_description("Mock LLM Agent")
            .add_additional_topic("PLAYER_INPUT")
            .listen_to_default_topic(False)
            .build_spec()
        )
        mock_llm: MockLLMAgent = guild._add_local_agent(mock_llm_spec)

        # Set up tool calls to return
        mock_llm.set_tool_calls([
            [ChatCompletionMessageToolCall(
                id="call_1",
                type="function",
                function=FunctionCall(name="search_suppliers", arguments="{}"),
            )],
            [ChatCompletionMessageToolCall(
                id="call_2",
                type="function",
                function=FunctionCall(name="check_inventory", arguments="{}"),
            )],
        ])

        # Add probe to send messages
        probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id("probe")
            .set_name("Probe")
            .set_description("Test probe")
            .listen_to_default_topic(True)
            .add_additional_topic("PLAYER_INPUT")
            .build_spec()
        )
        probe: ProbeAgent = guild._add_local_agent(probe_spec)

        time.sleep(0.3)

        # Send a ChatCompletionRequest to PLAYER_INPUT (simulating routed response)
        request = ChatCompletionRequest(
            messages=[{"role": "user", "content": "Simulation running! Day 1. What action would you like to take?"}]
        )
        probe.publish(
            topic="PLAYER_INPUT",
            payload=request,
        )

        time.sleep(0.5)

        # Verify MockLLMAgent received the request
        assert len(mock_llm.received_requests) >= 1, "MockLLMAgent should receive ChatCompletionRequest"
        assert "Simulation" in str(mock_llm.received_requests[0].messages[0].content)

        # Check if tool call was sent
        messages = probe.get_messages()
        print(f"\n[Test] Probe received {len(messages)} messages:")
        for m in messages:
            print(f"  - Format: {m.format}, Payload: {str(m.payload)[:100]}...")

        # Find ChatCompletionResponse
        responses = [m for m in messages if "ChatCompletionResponse" in m.format]
        assert len(responses) >= 1, "Should receive ChatCompletionResponse from MockLLMAgent"

        guild.shutdown()

    def test_tool_extraction_from_llm_response(self, messaging, org_id):
        """
        Test that ToolsManagerPlugin correctly extracts tool calls from LLM response.
        """
        toolset = VendingBenchToolspecsProvider()

        # Create a mock LLM response with a tool call
        response = ChatCompletionResponse(
            id="test",
            created=int(time.time()),
            choices=[
                Choice(
                    index=0,
                    message=AssistantMessage(
                        role="assistant",
                        content=None,
                        tool_calls=[
                            ChatCompletionMessageToolCall(
                                id="call_1",
                                type="function",
                                function=FunctionCall(
                                    name="search_suppliers",
                                    arguments='{"product_types": ["chips", "soda"]}',
                                ),
                            )
                        ],
                    ),
                    finish_reason="tool_calls",
                )
            ],
            model="test-model",
        )

        # Extract tool calls using ToolsHelper
        from rustic_ai.llm_agent.tools.tools_manager_plugin import ToolsHelper

        tool_calls = ToolsHelper.extract_tool_calls(toolset, response)

        assert len(tool_calls) == 1, "Should extract one tool call"
        assert isinstance(tool_calls[0], SupplierSearchRequest), f"Tool call should be SupplierSearchRequest, got {type(tool_calls[0])}"

        print(f"[Test] Extracted tool call: {tool_calls[0]}")

    def test_full_llm_agent_with_mock_llm(self, messaging, org_id):
        """
        Test the full LLMAgent with a mocked LLM dependency.

        This tests that:
        1. LLMAgent receives ChatCompletionRequest
        2. LLM is called with tools
        3. Tool calls are extracted and sent as messages
        """
        # Create guild
        guild = (
            GuildBuilder(guild_name="test_llm_guild", guild_description="Test LLM Guild")
            .set_messaging(messaging.backend_module, messaging.backend_class, messaging.backend_config)
            .launch(org_id)
        )

        # Create a mock LLM that returns tool calls
        mock_llm = MagicMock()
        mock_llm.completion.return_value = ChatCompletionResponse(
            id="test",
            created=int(time.time()),
            choices=[
                Choice(
                    index=0,
                    message=AssistantMessage(
                        role="assistant",
                        content=None,
                        tool_calls=[
                            ChatCompletionMessageToolCall(
                                id="call_1",
                                type="function",
                                function=FunctionCall(
                                    name="search_suppliers",
                                    arguments='{"product_types": ["chips"], "location": "local"}',
                                ),
                            )
                        ],
                    ),
                    finish_reason="tool_calls",
                )
            ],
            model="test-model",
        )

        # Add probe
        probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id("probe")
            .set_name("Probe")
            .set_description("Test probe")
            .listen_to_default_topic(True)
            .add_additional_topic("PLAYER_INPUT")
            .build_spec()
        )
        guild._add_local_agent(probe_spec)

        time.sleep(0.3)

        # Test that ToolsManagerPlugin preprocesses correctly
        plugin = ToolsManagerPlugin(
            toolset=VendingBenchToolspecsProvider()
        )

        request = ChatCompletionRequest(
            messages=[{"role": "user", "content": "Start the simulation"}]
        )

        # Preprocess should add tools
        preprocessed = plugin.preprocess(None, None, request, mock_llm)
        assert preprocessed.tools is not None, "Tools should be added to request"
        assert len(preprocessed.tools) > 0, "Should have tools"

        print(f"[Test] Preprocessed request has {len(preprocessed.tools)} tools")
        for tool in preprocessed.tools[:3]:
            print(f"  - {tool.function.name}")

        # Postprocess should extract tool calls
        tool_calls = plugin.postprocess(None, None, preprocessed, mock_llm.completion.return_value, mock_llm)
        assert tool_calls is not None, "Should extract tool calls"
        assert len(tool_calls) == 1, "Should have one tool call"
        assert isinstance(tool_calls[0], SupplierSearchRequest), f"Should be SupplierSearchRequest, got {type(tool_calls[0])}"

        print(f"[Test] Extracted tool call: {tool_calls[0]}")

        guild.shutdown()

    def test_agent_action_response_triggers_next_llm_call(self, messaging, org_id):
        """
        Test the critical flow: AgentActionResponse should trigger another LLM call.

        This is the flow that appears to be broken:
        1. AgentActionResponse arrives at PlayerGateway
        2. Routing transforms it to ChatCompletionRequest
        3. ChatCompletionRequest is sent to PLAYER_INPUT
        4. LLMAgent should receive it and call LLM again
        """
        guild = (
            GuildBuilder(guild_name="test_action_flow", guild_description="Test Action Flow")
            .set_messaging(messaging.backend_module, messaging.backend_class, messaging.backend_config)
            .launch(org_id)
        )

        # Add MockLLMAgent
        mock_llm_spec = (
            AgentBuilder(MockLLMAgent)
            .set_id("player_agent")
            .set_name("VendingBenchPlayer")
            .set_description("Mock LLM Agent")
            .add_additional_topic("PLAYER_INPUT")
            .listen_to_default_topic(False)
            .build_spec()
        )
        mock_llm: MockLLMAgent = guild._add_local_agent(mock_llm_spec)

        # Set up multiple tool calls
        mock_llm.set_tool_calls([
            [ChatCompletionMessageToolCall(id="call_1", type="function", function=FunctionCall(name="search_suppliers", arguments="{}"))],
            [ChatCompletionMessageToolCall(id="call_2", type="function", function=FunctionCall(name="check_inventory", arguments="{}"))],
            [ChatCompletionMessageToolCall(id="call_3", type="function", function=FunctionCall(name="end_day", arguments="{}"))],
        ])

        # Add probe
        probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id("probe")
            .set_name("Probe")
            .set_description("Test probe")
            .listen_to_default_topic(True)
            .add_additional_topic("PLAYER_INPUT")
            .build_spec()
        )
        probe: ProbeAgent = guild._add_local_agent(probe_spec)

        time.sleep(0.3)

        # Step 1: Send initial ChatCompletionRequest (simulating SimulationControlResponse transformed)
        print("\n=== Step 1: Sending initial ChatCompletionRequest ===")
        request1 = ChatCompletionRequest(
            messages=[{"role": "user", "content": "Simulation running! Day 1. What action would you like to take?"}]
        )
        probe.publish(topic="PLAYER_INPUT", payload=request1)
        time.sleep(0.5)

        assert mock_llm.call_count == 1, f"LLM should be called once, got {mock_llm.call_count}"
        print(f"[Test] LLM call count after step 1: {mock_llm.call_count}")

        # Step 2: Send another ChatCompletionRequest (simulating AgentActionResponse transformed)
        print("\n=== Step 2: Sending second ChatCompletionRequest (after tool result) ===")
        request2 = ChatCompletionRequest(
            messages=[{"role": "user", "content": "Action: search_suppliers - Success. Response: {...}. Day 1, sunny weather. What would you like to do next?"}]
        )
        probe.publish(topic="PLAYER_INPUT", payload=request2)
        time.sleep(0.5)

        assert mock_llm.call_count == 2, f"LLM should be called twice, got {mock_llm.call_count}"
        print(f"[Test] LLM call count after step 2: {mock_llm.call_count}")

        # Step 3: Send third ChatCompletionRequest
        print("\n=== Step 3: Sending third ChatCompletionRequest ===")
        request3 = ChatCompletionRequest(
            messages=[{"role": "user", "content": "Action: check_inventory - Success. Inventory: {...}. What would you like to do next?"}]
        )
        probe.publish(topic="PLAYER_INPUT", payload=request3)
        time.sleep(0.5)

        assert mock_llm.call_count == 3, f"LLM should be called three times, got {mock_llm.call_count}"
        print(f"[Test] LLM call count after step 3: {mock_llm.call_count}")

        # Verify all requests were received
        print(f"\n[Test] Total LLM calls: {mock_llm.call_count}")
        print(f"[Test] Total requests received: {len(mock_llm.received_requests)}")

        guild.shutdown()

    def test_routing_simulation_control_response_to_player_input(self, messaging, org_id):
        """
        Test that SimulationControlResponse is correctly transformed and routed to PLAYER_INPUT.

        This tests the routing rule:
        SimulationControlResponse -> ChatCompletionRequest -> PLAYER_INPUT
        """
        # This test verifies the JSONata transformation works correctly
        from jsonata import Jsonata

        # The transformation expression from the routing rule
        expression = "({'messages': [{'role': 'user', 'content': 'Simulation ' & $.simulation_status & '! Day: ' & $string($.simulation_time.current_day) & ', Weather: ' & $.simulation_time.weather & '. ' & $.message & ' What action would you like to take?'}]})"  # noqa: E501

        # Sample SimulationControlResponse payload
        payload = {
            "request_id": "test-123",
            "command": "start",
            "success": True,
            "message": "Simulation started",
            "simulation_status": "running",
            "simulation_time": {
                "current_day": 1,
                "current_time_minutes": 0,
                "is_daytime": True,
                "weather": "sunny",
                "day_of_week": 0,
            },
        }

        # Apply the transformation
        jsonata = Jsonata(expression)
        result = jsonata.evaluate(payload)

        print(f"[Test] Transformed result: {result}")

        assert "messages" in result, "Result should have 'messages' key"
        assert len(result["messages"]) == 1, "Should have one message"
        assert result["messages"][0]["role"] == "user", "Message role should be 'user'"
        assert "Simulation running" in result["messages"][0]["content"], "Content should mention simulation status"
        assert "Day: 1" in result["messages"][0]["content"], "Content should mention day"

    def test_routing_agent_action_response_to_player_input(self, messaging, org_id):
        """
        Test that AgentActionResponse is correctly transformed and routed to PLAYER_INPUT.

        This tests the routing rule:
        AgentActionResponse -> ChatCompletionRequest -> PLAYER_INPUT
        """
        from jsonata import Jsonata

        # The transformation expression from the routing rule
        expression = "({'messages': [{'role': 'user', 'content': 'Action: ' & $.action_type & ' - ' & ($.success ? 'Success' : 'Failed: ' & $.error_message) & '. Response: ' & $string($.response) & '. Day ' & $string($.simulation_time.current_day) & ', ' & $.simulation_time.weather & ' weather. What would you like to do next?'}]})"  # noqa: E501

        # Sample AgentActionResponse payload
        payload = {
            "request_id": "test-456",
            "action_type": "search_suppliers",
            "success": True,
            "response": {"suppliers": [{"name": "Test Supplier", "email": "test@supplier.com"}]},
            "simulation_time": {
                "current_day": 1,
                "current_time_minutes": 60,
                "is_daytime": True,
                "weather": "sunny",
                "day_of_week": 0,
            },
        }

        # Apply the transformation
        jsonata = Jsonata(expression)
        result = jsonata.evaluate(payload)

        print(f"[Test] Transformed result: {result}")

        assert "messages" in result, "Result should have 'messages' key"
        assert len(result["messages"]) == 1, "Should have one message"
        assert result["messages"][0]["role"] == "user", "Message role should be 'user'"
        assert "Action: search_suppliers" in result["messages"][0]["content"], "Content should mention action"
        assert "Success" in result["messages"][0]["content"], "Content should mention success"
        assert "Day 1" in result["messages"][0]["content"], "Content should mention day"


class TestRealLLMAgentFlow:
    """Test with the actual LLMAgent class to identify the issue."""

    @pytest.fixture
    def messaging(self) -> MessagingConfig:
        return MessagingConfig(
            backend_module="rustic_ai.core.messaging.backend",
            backend_class="InMemoryMessagingBackend",
            backend_config={},
        )

    def test_routing_with_gateway_agent(self, messaging, org_id):
        """
        Test the complete routing flow:
        GatewayAgent receives AgentActionResponse -> transforms -> sends to PLAYER_INPUT

        This simulates what happens when VendingBench responds to the player.
        """

        # Build the guild with routes that transform AgentActionResponse
        routes = RoutingSlip(steps=[
            RoutingRule(
                agent={"name": "TestGateway"},
                message_format="rustic_ai.showcase.vending_bench.messages.AgentActionResponse",
                transformer={
                    "style": "simple",
                    "output_format": "rustic_ai.core.guild.agent_ext.depends.llm.models.ChatCompletionRequest",
                    "expression": "({'messages': [{'role': 'user', 'content': 'Action: ' & $.action_type & ' - Success. What next?'}]})"
                },
                destination=RoutingDestination(topics="PLAYER_INPUT"),
                route_times=-1,
            ),
        ])

        guild = (
            GuildBuilder(guild_name="test_gateway_routing", guild_description="Test Gateway Routing")
            .set_messaging(messaging.backend_module, messaging.backend_class, messaging.backend_config)
            .set_routes(routes)
            .launch(org_id)
        )

        # Add MockLLMAgent to receive transformed messages
        mock_llm_spec = (
            AgentBuilder(MockLLMAgent)
            .set_id("player_agent")
            .set_name("VendingBenchPlayer")
            .set_description("Mock LLM Agent")
            .add_additional_topic("PLAYER_INPUT")
            .listen_to_default_topic(False)
            .build_spec()
        )
        mock_llm: MockLLMAgent = guild._add_local_agent(mock_llm_spec)

        # Set up tool calls
        mock_llm.set_tool_calls([
            [ChatCompletionMessageToolCall(id="call_1", type="function", function=FunctionCall(name="check_inventory", arguments="{}"))],
        ])

        # Add gateway agent
        gateway_spec = (
            AgentBuilder(GatewayAgent)
            .set_id("gateway")
            .set_name("TestGateway")
            .set_description("Test Gateway")
            .listen_to_default_topic(True)
            .set_properties({
                "input_formats": ["*"],
                "output_formats": ["*"],
                "returned_formats": ["rustic_ai.showcase.vending_bench.messages.AgentActionResponse"],
            })
            .build_spec()
        )
        guild._add_local_agent(gateway_spec)

        # Add probe to observe messages
        probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id("probe")
            .set_name("Probe")
            .set_description("Test probe")
            .listen_to_default_topic(True)
            .add_additional_topic("PLAYER_INPUT")
            .build_spec()
        )
        probe: ProbeAgent = guild._add_local_agent(probe_spec)

        time.sleep(0.3)

        # Now simulate what happens: Gateway receives AgentActionResponse
        # and should transform it to ChatCompletionRequest on PLAYER_INPUT

        # The gateway listens for messages with origin_guild_stack pointing to this guild
        # For testing, let's directly send an AgentActionResponse to the gateway
        # Note: In the real flow, this comes through G2G

        action_response = AgentActionResponse(
            request_id="test-123",
            action_type=ActionType.SEARCH_SUPPLIERS,
            success=True,
            response={"suppliers": []},
            simulation_time=SimulationTime(
                current_day=1,
                current_time_minutes=60,
                is_daytime=True,
                weather=WeatherType.SUNNY,
                day_of_week=0,
            ),
        )

        # Send directly to default topic to simulate internal routing
        # (In reality, the gateway processes this via handle_returned_response)
        probe.publish(topic="system", payload=action_response)

        time.sleep(0.5)

        # Check if MockLLMAgent received a ChatCompletionRequest
        print(f"\n[Test] MockLLMAgent received {len(mock_llm.received_requests)} requests")
        for i, req in enumerate(mock_llm.received_requests):
            print(f"  Request {i + 1}: {str(req.messages)[:100]}...")

        # The routing should transform AgentActionResponse to ChatCompletionRequest
        # But this might not work as expected because we're not going through the actual G2G flow
        # Let's just check what messages the probe sees
        messages = probe.get_messages()
        print(f"\n[Test] Probe received {len(messages)} messages:")
        for m in messages:
            print(f"  - Format: {m.format}")

        guild.shutdown()

        # This test helps us understand the routing behavior
        # The actual fix may need to be in the guild configuration or the routing logic
