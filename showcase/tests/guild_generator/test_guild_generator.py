"""Tests for the Guild Generator module."""

import json
import math

import pytest
from jsonata import Jsonata

from rustic_ai.core.agents.testutils import ProbeAgent
from rustic_ai.core.guild import GuildTopics
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.ui_protocol.types import VegaLiteFormat
from rustic_ai.showcase.guild_generator.models import (
    ActionType,
    AgentLookupRequest,
    AgentLookupResponse,
    ExportRequest,
    ExportResponse,
    FlowchartUpdateRequest,
    GuildBuilderState,
    OrchestratorAction,
    RouteRequest,
    RouteResponse,
    TransformationSpec,
    TransformRequest,
    TransformResponse,
)
from rustic_ai.showcase.guild_generator.flowchart_agent import FlowchartAgent


class TestModels:
    """Tests for the Guild Generator models."""

    def test_orchestrator_action_creation(self):
        """Test that OrchestratorAction can be created properly."""
        action = OrchestratorAction(
            action=ActionType.ADD_AGENT,
            details={"purpose": "summarize text"},
            user_message="@Orchestrator add an LLM agent",
        )
        assert action.action == ActionType.ADD_AGENT
        assert action.details["purpose"] == "summarize text"

    def test_guild_builder_state_default(self):
        """Test default GuildBuilderState values."""
        state = GuildBuilderState()
        assert state.name == "New Guild"
        assert state.description == "A guild created with Guild Generator"
        assert state.agents == []
        assert state.routes == []

    def test_guild_builder_state_with_agents(self):
        """Test GuildBuilderState with agents."""
        state = GuildBuilderState(
            name="Test Guild",
            agents=[
                {
                    "id": "agent_1",
                    "name": "Test Agent",
                    "class_name": "test.Agent",
                    "description": "Test",
                }
            ],
            routes=[],
        )
        assert state.name == "Test Guild"
        assert len(state.agents) == 1
        assert state.agents[0]["id"] == "agent_1"

    def test_transformation_spec(self):
        """Test TransformationSpec model."""
        spec = TransformationSpec(
            style="content_based_router",
            expression_type="jsonata",
            handler="({\"topics\": \"OUTPUT\"})",
        )
        assert spec.style == "content_based_router"
        assert spec.handler == "({\"topics\": \"OUTPUT\"})"

    def test_action_types_enum(self):
        """Test all action types are defined."""
        assert ActionType.ADD_AGENT == "add_agent"
        assert ActionType.ADD_ROUTE == "add_route"
        assert ActionType.SHOW_FLOW == "show_flow"
        assert ActionType.PUBLISH == "publish"
        assert ActionType.HELP == "help"


class TestJSONataTransformations:
    """Tests for JSONata transformations used in the blueprint."""

    def test_orchestrator_routing_transform(self):
        """Test the orchestrator routing content-based router."""
        expression = """($.payload.action = 'add_agent' ? {"topics": "AGENT_LOOKUP"} : $.payload.action = 'add_route' ? {"topics": "ROUTE_BUILD"} : $.payload.action = 'show_flow' ? {"topics": "FLOWCHART"} : $.payload.action = 'publish' ? {"topics": "EXPORT"} : {"topics": "STATE_MGMT"})"""

        expr = Jsonata(expression)

        # Test add_agent action
        result = expr.evaluate({"payload": {"action": "add_agent"}})
        assert result["topics"] == "AGENT_LOOKUP"

        # Test add_route action
        result = expr.evaluate({"payload": {"action": "add_route"}})
        assert result["topics"] == "ROUTE_BUILD"

        # Test show_flow action
        result = expr.evaluate({"payload": {"action": "show_flow"}})
        assert result["topics"] == "FLOWCHART"

        # Test publish action
        result = expr.evaluate({"payload": {"action": "publish"}})
        assert result["topics"] == "EXPORT"

        # Test help action (default case)
        result = expr.evaluate({"payload": {"action": "help"}})
        assert result["topics"] == "STATE_MGMT"

    def test_user_proxy_routing_transform(self):
        """Test the user proxy routing for @Orchestrator detection."""
        expression = """($contains($.payload.messages[0].content[0].text, '@Orchestrator') ? {"topics": "ORCHESTRATOR", "recipient_list": [{"name": "Orchestrator"}]} : {"topics": "TEST_FLOW"})"""

        expr = Jsonata(expression)

        # Test message with @Orchestrator tag
        result = expr.evaluate(
            {"payload": {"messages": [{"content": [{"text": "@Orchestrator add an agent"}]}]}}
        )
        assert result["topics"] == "ORCHESTRATOR"
        assert result["recipient_list"][0]["name"] == "Orchestrator"

        # Test message without @Orchestrator tag
        result = expr.evaluate(
            {"payload": {"messages": [{"content": [{"text": "Hello, test this"}]}]}}
        )
        assert result["topics"] == "TEST_FLOW"

    def test_agent_append_transform(self):
        """Test the guild state update for adding agents."""
        expression = """({"guild_builder": {"agents": $append($.guild_state.guild_builder.agents ? $.guild_state.guild_builder.agents : [], $.payload.agent_spec)}})"""

        expr = Jsonata(expression)

        # Test with empty initial state
        result = expr.evaluate(
            {
                "guild_state": {"guild_builder": {"agents": []}},
                "payload": {
                    "agent_spec": {
                        "id": "new_agent",
                        "name": "New Agent",
                    }
                },
            }
        )
        assert len(result["guild_builder"]["agents"]) == 1
        assert result["guild_builder"]["agents"][0]["id"] == "new_agent"

        # Test with existing agents
        result = expr.evaluate(
            {
                "guild_state": {
                    "guild_builder": {
                        "agents": [{"id": "existing_agent", "name": "Existing"}]
                    }
                },
                "payload": {
                    "agent_spec": {
                        "id": "new_agent",
                        "name": "New Agent",
                    }
                },
            }
        )
        assert len(result["guild_builder"]["agents"]) == 2
        assert result["guild_builder"]["agents"][0]["id"] == "existing_agent"
        assert result["guild_builder"]["agents"][1]["id"] == "new_agent"

    def test_route_append_transform(self):
        """Test the guild state update for adding routes."""
        expression = """({"guild_builder": {"routes": $append($.guild_state.guild_builder.routes ? $.guild_state.guild_builder.routes : [], $.payload.routing_rule)}})"""

        expr = Jsonata(expression)

        # Test with empty initial state
        result = expr.evaluate(
            {
                "guild_state": {"guild_builder": {"routes": []}},
                "payload": {
                    "routing_rule": {
                        "agent": {"name": "Test Agent"},
                        "message_format": "test.Format",
                    }
                },
            }
        )
        assert len(result["guild_builder"]["routes"]) == 1
        assert result["guild_builder"]["routes"][0]["agent"]["name"] == "Test Agent"

    def test_dynamic_agent_specs_append_transform(self):
        """Test the guild state update for adding dynamic agent specs."""
        expression = """({"dynamic_agent_specs": $append($.guild_state.dynamic_agent_specs ? $.guild_state.dynamic_agent_specs : [], $.payload.agent_spec)})"""

        expr = Jsonata(expression)

        # Test with no existing dynamic_agent_specs (undefined)
        result = expr.evaluate(
            {
                "guild_state": {},
                "payload": {
                    "agent_spec": {
                        "id": "dynamic_agent",
                        "name": "Dynamic Agent",
                        "class_name": "test.DynamicAgent",
                    }
                },
            }
        )
        assert len(result["dynamic_agent_specs"]) == 1
        assert result["dynamic_agent_specs"][0]["id"] == "dynamic_agent"

        # Test with existing dynamic_agent_specs
        result = expr.evaluate(
            {
                "guild_state": {
                    "dynamic_agent_specs": [
                        {"id": "existing", "name": "Existing Agent"}
                    ]
                },
                "payload": {
                    "agent_spec": {
                        "id": "new_dynamic",
                        "name": "New Dynamic Agent",
                    }
                },
            }
        )
        assert len(result["dynamic_agent_specs"]) == 2
        assert result["dynamic_agent_specs"][0]["id"] == "existing"
        assert result["dynamic_agent_specs"][1]["id"] == "new_dynamic"

    def test_agent_spec_extraction_transform(self):
        """Test the agent spec extraction transformer."""
        expression = """({"agent_spec": $.payload.agent_spec})"""

        expr = Jsonata(expression)

        result = expr.evaluate(
            {
                "payload": {
                    "agent_spec": {
                        "id": "test_agent",
                        "name": "Test Agent",
                        "class_name": "test.TestAgent",
                        "description": "A test agent",
                    },
                    "other_field": "should be ignored",
                }
            }
        )
        assert "agent_spec" in result
        assert result["agent_spec"]["id"] == "test_agent"
        assert result["agent_spec"]["name"] == "Test Agent"
        assert "other_field" not in result


class TestFlowchartAgent:
    """Tests for the FlowchartAgent."""

    def test_build_flowchart_spec_empty(self):
        """Test flowchart generation with no agents."""
        # Create a minimal agent instance for testing
        agent = FlowchartAgent.__new__(FlowchartAgent)
        agent._props = type("Props", (), {"default_width": 600, "default_height": 400})()

        # Mock config
        class MockConfig:
            default_width = 600
            default_height = 400

        agent.config = MockConfig()

        spec = agent._build_flowchart_spec(None)

        assert spec["$schema"] == "https://vega.github.io/schema/vega-lite/v5.json"
        assert spec["width"] == 600
        assert spec["height"] == 400
        # 2 layers (nodes, labels) when no edges - edges layer excluded to avoid Vega-Lite errors
        assert len(spec["layer"]) == 2

    def test_build_flowchart_spec_with_agents(self):
        """Test flowchart generation with agents."""
        agent = FlowchartAgent.__new__(FlowchartAgent)

        class MockConfig:
            default_width = 600
            default_height = 400

        agent.config = MockConfig()

        state = GuildBuilderState(
            name="Test Guild",
            description="Test description",
            agents=[
                {
                    "id": "agent_1",
                    "name": "Agent One",
                    "class_name": "test.LLMAgent",
                }
            ],
            routes=[],
        )

        spec = agent._build_flowchart_spec(state)

        assert spec["title"]["text"] == "Test Guild"
        assert spec["title"]["subtitle"] == "Test description"

        # Check that agent nodes are included
        nodes_layer = spec["layer"][1]
        nodes_data = nodes_layer["data"]["values"]

        # Should have UserProxyAgent + our agent
        assert len(nodes_data) == 2
        agent_names = [n["name"] for n in nodes_data]
        assert "UserProxyAgent" in agent_names
        assert "Agent One" in agent_names

    def test_build_edge_data(self):
        """Test edge data generation for routes."""
        agent = FlowchartAgent.__new__(FlowchartAgent)

        agents = [
            {"id": "a1", "name": "Agent1", "x": 100, "y": 100},
            {"id": "a2", "name": "Agent2", "x": 200, "y": 200},
        ]

        routes = [
            {"source": "Agent1", "target": "Agent2", "format": "TestFormat"}
        ]

        edges = agent._build_edge_data(agents, routes)

        assert len(edges) == 1
        assert edges[0]["x1"] == 100
        assert edges[0]["y1"] == 100
        assert edges[0]["x2"] == 200
        assert edges[0]["y2"] == 200


class TestBlueprintValidity:
    """Tests to validate the blueprint JSON."""

    def test_blueprint_loads(self):
        """Test that the blueprint JSON can be loaded."""
        import os

        blueprint_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "apps",
            "guild_generator_blueprint.json",
        )

        with open(blueprint_path) as f:
            blueprint = json.load(f)

        assert blueprint["name"] == "Guild Generator"
        assert "spec" in blueprint
        assert "agents" in blueprint["spec"]
        assert "routes" in blueprint["spec"]

    def test_blueprint_agents_valid(self):
        """Test that all agents in the blueprint have required fields."""
        import os

        blueprint_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "apps",
            "guild_generator_blueprint.json",
        )

        with open(blueprint_path) as f:
            blueprint = json.load(f)

        agents = blueprint["spec"]["agents"]

        for agent in agents:
            assert "id" in agent, f"Agent missing id: {agent}"
            assert "name" in agent, f"Agent missing name: {agent}"
            assert "description" in agent, f"Agent missing description: {agent}"
            assert "class_name" in agent, f"Agent missing class_name: {agent}"
            assert "." in agent["class_name"], f"Invalid class_name format: {agent['class_name']}"

    def test_blueprint_routes_valid(self):
        """Test that all routes in the blueprint have required structure."""
        import os

        blueprint_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "apps",
            "guild_generator_blueprint.json",
        )

        with open(blueprint_path) as f:
            blueprint = json.load(f)

        routes = blueprint["spec"]["routes"]["steps"]

        for i, route in enumerate(routes):
            # Must have either agent or agent_type
            has_agent = route.get("agent") is not None
            has_agent_type = route.get("agent_type") is not None
            assert has_agent or has_agent_type, f"Route {i} must have agent or agent_type"

    def test_blueprint_jsonata_expressions_valid(self):
        """Test that all JSONata expressions in the blueprint are valid."""
        import os

        blueprint_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "apps",
            "guild_generator_blueprint.json",
        )

        with open(blueprint_path) as f:
            blueprint = json.load(f)

        routes = blueprint["spec"]["routes"]["steps"]

        for i, route in enumerate(routes):
            # Check transformer expression
            transformer = route.get("transformer")
            if transformer and transformer.get("handler"):
                handler = transformer["handler"]
                try:
                    expr = Jsonata(handler)
                    assert not expr.errors, f"Route {i} transformer has invalid JSONata: {expr.errors}"
                except Exception as e:
                    pytest.fail(f"Route {i} transformer failed to parse: {e}")

            # Check guild_state_update expression
            guild_state_update = route.get("guild_state_update")
            if guild_state_update and guild_state_update.get("state_update"):
                state_update = guild_state_update["state_update"]
                try:
                    expr = Jsonata(state_update)
                    assert not expr.errors, f"Route {i} guild_state_update has invalid JSONata: {expr.errors}"
                except Exception as e:
                    pytest.fail(f"Route {i} guild_state_update failed to parse: {e}")

    def test_blueprint_transformer_style_field_compatibility(self):
        """Test that transformers have the correct style/field combinations.

        - style: "simple" (PayloadTransformer) requires 'expression' field
        - style: "content_based_router" (FunctionalTransformer) requires 'handler' field
        """
        import os

        blueprint_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "apps",
            "guild_generator_blueprint.json",
        )

        with open(blueprint_path) as f:
            blueprint = json.load(f)

        routes = blueprint["spec"]["routes"]["steps"]

        for i, route in enumerate(routes):
            transformer = route.get("transformer")
            if transformer is None:
                continue

            style = transformer.get("style", "simple")  # default is "simple"
            has_handler = "handler" in transformer and transformer["handler"]
            has_expression = "expression" in transformer and transformer["expression"]

            if style == "simple":
                # PayloadTransformer uses 'expression' field
                assert has_expression or not has_handler, (
                    f"Route {i}: style='simple' (PayloadTransformer) should use 'expression' field, not 'handler'. "
                    f"Either change style to 'content_based_router' or rename 'handler' to 'expression'."
                )
            elif style == "content_based_router":
                # FunctionalTransformer uses 'handler' field
                assert has_handler, (
                    f"Route {i}: style='content_based_router' (FunctionalTransformer) requires 'handler' field."
                )

    def test_blueprint_state_update_has_expression_type(self):
        """Test that all guild_state_update and agent_state_update have expression_type."""
        import os

        blueprint_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "apps",
            "guild_generator_blueprint.json",
        )

        with open(blueprint_path) as f:
            blueprint = json.load(f)

        routes = blueprint["spec"]["routes"]["steps"]

        for i, route in enumerate(routes):
            # Check guild_state_update
            guild_state_update = route.get("guild_state_update")
            if guild_state_update and guild_state_update.get("state_update"):
                assert "expression_type" in guild_state_update, (
                    f"Route {i}: guild_state_update has state_update but missing expression_type"
                )
                assert guild_state_update["expression_type"] in ("jsonata", "cel"), (
                    f"Route {i}: guild_state_update expression_type must be 'jsonata' or 'cel'"
                )

            # Check agent_state_update
            agent_state_update = route.get("agent_state_update")
            if agent_state_update and agent_state_update.get("state_update"):
                assert "expression_type" in agent_state_update, (
                    f"Route {i}: agent_state_update has state_update but missing expression_type"
                )
                assert agent_state_update["expression_type"] in ("jsonata", "cel"), (
                    f"Route {i}: agent_state_update expression_type must be 'jsonata' or 'cel'"
                )


class TestStateManagerAgent:
    """Tests for the StateManagerAgent with race condition handling."""

    def test_state_manager_handles_concurrent_agent_additions(self, org_id):
        """Test that StateManagerAgent correctly handles multiple agents added in quick succession (race condition fix)."""
        from rustic_ai.showcase.guild_generator.state_manager import StateManagerAgent
        from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name

        # Build a guild with state manager
        builder = GuildBuilder(
            guild_name="State Manager Test",
            guild_description="Test for concurrent state updates",
        ).set_messaging(
            "rustic_ai.core.messaging.backend",
            "InMemoryMessagingBackend",
            {},
        )

        # Add state manager agent
        state_manager_spec = (
            AgentBuilder(StateManagerAgent)
            .set_id("state_manager")
            .set_name("State Manager")
            .set_description("Manages guild builder state")
            .add_additional_topic("STATE_MGMT")
            .build_spec()
        )

        builder.add_agent_spec(state_manager_spec)
        guild = builder.launch(org_id)

        # Add probe to capture outgoing messages
        probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id("probe_agent")
            .set_name("Probe Agent")
            .set_description("Captures messages for testing")
            .add_additional_topic("STATE_MGMT")
            .add_additional_topic(GuildTopics.DEFAULT_TOPICS[0])
            .build_spec()
        )

        probe_agent: ProbeAgent = guild._add_local_agent(probe_spec)

        # Send two AgentLookupResponse messages back-to-back (simulating race condition)
        agent_lookup_response_1 = AgentLookupResponse(
            agent_spec={
                "id": "agent_1",
                "name": "Agent One",
                "description": "First agent",
                "class_name": "test.AgentOne",
                "additional_topics": [],
                "properties": {},
                "listen_to_default_topic": True,
                "act_only_when_tagged": False,
            },
            explanation="First agent added",
            input_formats=["test.InputFormat1"],
            output_formats=["test.OutputFormat1"],
        )

        agent_lookup_response_2 = AgentLookupResponse(
            agent_spec={
                "id": "agent_2",
                "name": "Agent Two",
                "description": "Second agent",
                "class_name": "test.AgentTwo",
                "additional_topics": [],
                "properties": {},
                "listen_to_default_topic": True,
                "act_only_when_tagged": False,
            },
            explanation="Second agent added",
            input_formats=["test.InputFormat2"],
            output_formats=["test.OutputFormat2"],
        )

        # Send both messages quickly
        probe_agent.publish_dict(
            "STATE_MGMT",
            agent_lookup_response_1.model_dump(),
            format=get_qualified_class_name(AgentLookupResponse),
        )

        probe_agent.publish_dict(
            "STATE_MGMT",
            agent_lookup_response_2.model_dump(),
            format=get_qualified_class_name(AgentLookupResponse),
        )

        # Wait for processing
        import time
        time.sleep(1.0)

        # Verify both agents are in the guild state by checking messages sent
        # The StateManagerAgent should have sent TextFormat messages for both agents
        messages = probe_agent.get_messages()

        from rustic_ai.core.ui_protocol.types import TextFormat
        text_messages = [
            m for m in messages
            if m.format == get_qualified_class_name(TextFormat)
        ]

        # Should have received 2 TextFormat messages (one for each agent added)
        assert len(text_messages) >= 2, f"Expected at least 2 TextFormat messages, got {len(text_messages)}"

        # Verify the content mentions both agents
        all_text = " ".join([m.payload.get("text", "") for m in text_messages])
        assert "Agent One" in all_text, f"Agent One not mentioned in messages: {all_text[:200]}"
        assert "Agent Two" in all_text, f"Agent Two not mentioned in messages: {all_text[:200]}"

    def test_state_manager_handles_concurrent_route_additions(self, org_id):
        """Test that StateManagerAgent correctly handles multiple routes added in quick succession."""
        from rustic_ai.showcase.guild_generator.state_manager import StateManagerAgent
        from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name

        # Build a guild with state manager
        builder = GuildBuilder(
            guild_name="Route State Manager Test",
            guild_description="Test for concurrent route updates",
        ).set_messaging(
            "rustic_ai.core.messaging.backend",
            "InMemoryMessagingBackend",
            {},
        )

        # Add state manager agent
        state_manager_spec = (
            AgentBuilder(StateManagerAgent)
            .set_id("state_manager")
            .set_name("State Manager")
            .set_description("Manages guild builder state")
            .add_additional_topic("STATE_MGMT")
            .build_spec()
        )

        builder.add_agent_spec(state_manager_spec)
        guild = builder.launch(org_id)

        # Add probe
        probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id("probe_agent")
            .set_name("Probe Agent")
            .set_description("Captures messages for testing")
            .add_additional_topic("STATE_MGMT")
            .build_spec()
        )

        probe_agent: ProbeAgent = guild._add_local_agent(probe_spec)

        # Send two RouteResponse messages back-to-back
        route_response_1 = RouteResponse(
            routing_rule={
                "agent": {"name": "Agent One"},
                "message_format": "test.Format1",
                "destination": {"topics": "OUTPUT1"},
            },
            explanation="First route added",
        )

        route_response_2 = RouteResponse(
            routing_rule={
                "agent": {"name": "Agent Two"},
                "message_format": "test.Format2",
                "destination": {"topics": "OUTPUT2"},
            },
            explanation="Second route added",
        )

        # Send both messages quickly
        probe_agent.publish_dict(
            "STATE_MGMT",
            route_response_1.model_dump(),
            format=get_qualified_class_name(RouteResponse),
        )

        probe_agent.publish_dict(
            "STATE_MGMT",
            route_response_2.model_dump(),
            format=get_qualified_class_name(RouteResponse),
        )

        # Wait for processing
        import time
        time.sleep(1.0)

        # Verify both routes are in the guild state by checking messages sent
        messages = probe_agent.get_messages()

        from rustic_ai.core.ui_protocol.types import TextFormat
        text_messages = [
            m for m in messages
            if m.format == get_qualified_class_name(TextFormat)
        ]

        # Should have received 2 TextFormat messages (one for each route added)
        assert len(text_messages) >= 2, f"Expected at least 2 TextFormat messages, got {len(text_messages)}"

        # Verify the content mentions both routes
        all_text = " ".join([m.payload.get("text", "") for m in text_messages])
        assert "Agent One" in all_text or "OUTPUT1" in all_text, f"First route not mentioned: {all_text[:200]}"
        assert "Agent Two" in all_text or "OUTPUT2" in all_text, f"Second route not mentioned: {all_text[:200]}"


class TestGuildGeneratorIntegration:
    """Integration tests for the guild generator."""

    def test_guild_generator_starts(self, org_id):
        """Test that the guild generator can be started."""
        from rustic_ai.showcase.guild_generator.flowchart_agent import FlowchartAgent
        from rustic_ai.showcase.guild_generator.state_manager import StateManagerAgent

        # Build a minimal guild with just the flowchart and state manager agents
        builder = GuildBuilder(
            guild_name="Guild Generator Test",
            guild_description="Test guild for guild generator",
        ).set_messaging(
            "rustic_ai.core.messaging.backend",
            "InMemoryMessagingBackend",
            {},
        )

        # Add flowchart agent
        flowchart_spec = (
            AgentBuilder(FlowchartAgent)
            .set_id("flowchart_agent")
            .set_name("Flowchart Agent")
            .set_description("Generates VegaLite visualizations")
            .add_additional_topic("FLOWCHART")
            .build_spec()
        )

        # Add state manager agent
        state_manager_spec = (
            AgentBuilder(StateManagerAgent)
            .set_id("state_manager")
            .set_name("State Manager")
            .set_description("Manages guild builder state")
            .add_additional_topic("STATE_MGMT")
            .build_spec()
        )

        builder.add_agent_spec(flowchart_spec)
        builder.add_agent_spec(state_manager_spec)

        guild = builder.launch(org_id)

        # Add probe to capture messages
        probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id("probe_agent")
            .set_name("Probe Agent")
            .set_description("Captures messages for testing")
            .add_additional_topic("FLOWCHART")
            .add_additional_topic("STATE_MGMT")
            .add_additional_topic(GuildTopics.DEFAULT_TOPICS[0])
            .build_spec()
        )

        probe_agent: ProbeAgent = guild._add_local_agent(probe_spec)

        # Send flowchart update request
        from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name

        probe_agent.publish_dict(
            "FLOWCHART",
            {"trigger": "update"},
            format=get_qualified_class_name(FlowchartUpdateRequest),
        )

        import time
        time.sleep(0.5)

        messages = probe_agent.get_messages()

        # Should have received a VegaLiteFormat
        viz_messages = [
            m for m in messages
            if m.format == get_qualified_class_name(VegaLiteFormat)
        ]

        assert len(viz_messages) >= 1, f"Expected VegaLiteFormat message, got: {[m.format for m in messages]}"

        # Verify the flowchart content
        flowchart = viz_messages[0].payload
        assert "$schema" in flowchart["spec"]
        assert "layer" in flowchart["spec"]


class TestAgentRegistryDependencySpec:
    """Tests to validate that agent registry dependencies have correct DependencySpec format.

    NOTE: These tests are skipped because AGENT_REGISTRY is no longer a static constant.
    All agents are now loaded from the API at runtime.
    """

    @pytest.mark.skip(reason="AGENT_REGISTRY is now loaded from API, not a static constant")
    def test_registry_dependencies_have_valid_dependency_spec_format(self):
        """Test that all required_dependencies in AGENT_REGISTRY use proper DependencySpec format."""
        pass

    @pytest.mark.skip(reason="AGENT_REGISTRY is now loaded from API, not a static constant")
    def test_dependency_map_validates_as_dependency_spec_dict(self):
        """Test that dependency_map values from registry can be validated as DependencySpec."""
        pass

    @pytest.mark.skip(reason="AGENT_REGISTRY is now loaded from API, not a static constant")
    def test_llm_agent_dependency_spec_is_valid(self):
        """Specific test for LLMAgent which was the original failing case."""
        pass

    @pytest.mark.skip(reason="AGENT_REGISTRY is now loaded from API, not a static constant")
    def test_react_agent_dependency_spec_is_valid(self):
        """Test for ReactAgent which also has llm dependency."""
        pass
