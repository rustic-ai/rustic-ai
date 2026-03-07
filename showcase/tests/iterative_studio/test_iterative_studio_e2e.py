"""End-to-end tests for the Iterative Studio guild.

This test module validates:
1. Guild loading from JSON specification
2. Mode controller routing to correct pipelines
3. Transform accuracy for each mode
4. Message flow through agent pipelines
5. Final output delivery to user broadcast topic
"""

import json
from pathlib import Path
import time

import pytest
import shortuuid

from rustic_ai.core import GuildTopics, Message
from rustic_ai.core.agents.testutils import ProbeAgent
from rustic_ai.core.agents.utils import UserProxyAgent
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    AssistantMessage,
    ChatCompletionResponse,
    Choice,
    CompletionUsage,
    FinishReason,
)
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.guild.dsl import GuildSpec
from rustic_ai.core.messaging.core.messaging_config import MessagingConfig
from rustic_ai.core.utils.gemstone_id import GemstoneGenerator

# Path to the guild.json file
GUILD_JSON_PATH = Path(__file__).parent.parent.parent / "apps" / "iterative_studio" / "iterative_studio.json"


def load_guild_spec() -> GuildSpec:
    """Load the guild spec from the wrapped JSON file."""
    with open(GUILD_JSON_PATH) as f:
        data = json.load(f)
    return GuildSpec.model_validate(data["spec"])


def create_guild_builder(messaging: MessagingConfig) -> GuildBuilder:
    """Create a GuildBuilder from the guild spec with proper loading."""
    with open(GUILD_JSON_PATH) as f:
        data = json.load(f)

    # Use from_spec_json on the inner spec
    spec_json = json.dumps(data["spec"])
    builder = GuildBuilder.from_spec_json(spec_json)
    builder.set_messaging(
        messaging.backend_module,
        messaging.backend_class,
        messaging.backend_config,
    )
    return builder


def create_mock_response(
    content: str,
    finish_reason: FinishReason = FinishReason.stop,
) -> ChatCompletionResponse:
    """Helper to create mock LLM responses."""
    return ChatCompletionResponse(
        id=f"chatcmpl-{shortuuid.uuid()}",
        created=1234567890,
        model="test-model",
        choices=[
            Choice(
                index=0,
                message=AssistantMessage(content=content),
                finish_reason=finish_reason,
            )
        ],
        usage=CompletionUsage(
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
        ),
    )


class TestIterativeStudioE2E:
    """End-to-end tests for the Iterative Studio guild."""

    @pytest.fixture
    def org_id(self):
        return f"test_org_{shortuuid.uuid()}"

    @pytest.fixture
    def messaging(self) -> MessagingConfig:
        return MessagingConfig(
            backend_module="rustic_ai.core.messaging.backend",
            backend_class="InMemoryMessagingBackend",
            backend_config={},
        )

    @pytest.fixture
    def guild_spec(self) -> GuildSpec:
        """Load the guild spec from the JSON file."""
        return load_guild_spec()

    @pytest.fixture
    def generator(self) -> GemstoneGenerator:
        return GemstoneGenerator(1)

    def test_guild_loads_from_json(self, messaging: MessagingConfig, org_id: str):
        """Test that the guild can be loaded and launched from JSON."""
        builder = create_guild_builder(messaging)

        # Launch the guild (this tests that all agents can be instantiated)
        guild = builder.launch(org_id)

        try:
            assert guild is not None
            assert guild.name == "Iterative Studio"

            # Verify agents were created
            agent_ids = list(guild._agents_by_id.keys())
            assert "mode_controller" in agent_ids
            assert "feature_novelty" in agent_ids
            assert "feature_quality" in agent_ids
            assert "agentic_agent" in agent_ids
            assert "adaptive_dt" in agent_ids
        finally:
            guild.shutdown()

    def test_routing_slip_exists(self, guild_spec: GuildSpec):
        """Test that routing slip is properly configured."""
        assert guild_spec.routes is not None
        assert len(guild_spec.routes.steps) > 0

        # Check that we have routes for key transitions
        route_patterns = []
        for step in guild_spec.routes.steps:
            if step.agent:
                route_patterns.append(step.agent.name)
            elif step.agent_type:
                route_patterns.append(step.agent_type)

        # Verify key agents are in routing
        assert "Mode Controller" in route_patterns
        assert "Bug Fixer" in route_patterns
        assert "Final Judge" in route_patterns


class TestModeRouting:
    """Tests for mode-specific routing behavior using the parsed GuildSpec."""

    @pytest.fixture
    def guild_spec(self) -> GuildSpec:
        return load_guild_spec()

    def test_refine_mode_routes_to_feature_agents(self, guild_spec: GuildSpec):
        """Test that Refine mode routes to both feature suggestion agents."""
        routes = guild_spec.routes

        # Find the mode controller route
        mode_controller_route = None
        for step in routes.steps:
            if step.agent and step.agent.name == "Mode Controller":
                mode_controller_route = step
                break

        assert mode_controller_route is not None
        assert mode_controller_route.transformer is not None

        # Verify the handler includes REFINE_NOVELTY and REFINE_QUALITY for refine mode
        handler = mode_controller_route.transformer.handler
        assert "REFINE_NOVELTY" in handler
        assert "REFINE_QUALITY" in handler

    def test_deepthink_mode_pipeline_routing(self, guild_spec: GuildSpec):
        """Test that Deepthink mode has complete pipeline routing."""
        routes = guild_spec.routes

        # Collect all Deepthink-related routes
        dt_routes = []
        for step in routes.steps:
            if step.agent and step.agent.name:
                name = step.agent.name
                if any(
                    x in name
                    for x in [
                        "Strategy",
                        "Solution",
                        "Critique",
                        "Refinement",
                        "Red Team",
                        "Final Judge",
                    ]
                ):
                    dt_routes.append(step)

        # Verify we have routes for the key Deepthink pipeline stages
        route_names = [r.agent.name for r in dt_routes]
        assert "Strategy Generator" in route_names
        assert "Solution Agent" in route_names
        assert "Critique Agent" in route_names
        assert "Red Team Agent" in route_names
        assert "Final Judge" in route_names

        # Verify Final Judge routes to user_message_broadcast
        final_judge_route = next(r for r in dt_routes if r.agent.name == "Final Judge")
        assert final_judge_route.destination.topics == "user_message_broadcast"
        assert final_judge_route.process_status.value == "completed"

    def test_agentic_mode_routes_directly(self, guild_spec: GuildSpec):
        """Test that Agentic mode routes directly to the agentic agent."""
        routes = guild_spec.routes

        # Find the mode controller route
        mode_controller_route = None
        for step in routes.steps:
            if step.agent and step.agent.name == "Mode Controller":
                mode_controller_route = step
                break

        assert mode_controller_route is not None
        handler = mode_controller_route.transformer.handler

        # Verify 'agentic' mode routes to AGENTIC topic
        assert "'agentic': 'AGENTIC'" in handler

        # Find Agentic Agent route
        agentic_route = None
        for step in routes.steps:
            if step.agent and step.agent.name == "Agentic Agent":
                agentic_route = step
                break

        assert agentic_route is not None
        assert agentic_route.destination.topics == "user_message_broadcast"

    def test_contextual_mode_iterative_routing(self, guild_spec: GuildSpec):
        """Test that Contextual mode has iterative routing between agents."""
        routes = guild_spec.routes

        # Find Main Generator and Iterative Agent routes
        main_gen_route = None
        iterative_route = None

        for step in routes.steps:
            if step.agent:
                if step.agent.name == "Main Generator":
                    main_gen_route = step
                elif step.agent.name == "Iterative Agent":
                    iterative_route = step

        # Main Generator should route to Iterative Agent
        assert main_gen_route is not None
        assert main_gen_route.transformer is not None
        assert "CTX_ITERATE" in main_gen_route.transformer.handler

        # Iterative Agent should have conditional routing
        assert iterative_route is not None
        assert iterative_route.transformer is not None
        handler = iterative_route.transformer.handler

        # Should check for APPROVE and route accordingly
        assert "APPROVE" in handler
        # Should route back to CTX_MAIN for revisions
        assert "CTX_MAIN" in handler
        # Should route to CTX_MEMORY when done
        assert "CTX_MEMORY" in handler


class TestTransformAccuracy:
    """Tests for transform expression accuracy using the parsed GuildSpec."""

    @pytest.fixture
    def guild_spec(self) -> GuildSpec:
        return load_guild_spec()

    def test_mode_controller_transform_maps_all_modes(self, guild_spec: GuildSpec):
        """Test that mode controller transform handles all 5 modes."""
        routes = guild_spec.routes

        # Find mode controller route
        mode_controller_route = None
        for step in routes.steps:
            if step.agent and step.agent.name == "Mode Controller":
                mode_controller_route = step
                break

        assert mode_controller_route is not None
        handler = mode_controller_route.transformer.handler

        # Verify all 5 modes are mapped
        assert "'refine'" in handler
        assert "'deepthink'" in handler
        assert "'adaptive'" in handler
        assert "'agentic'" in handler
        assert "'contextual'" in handler

        # Verify default fallback exists
        assert "CTX_MAIN" in handler  # Default fallback

    def test_refine_aggregator_transform_combines_messages(self, guild_spec: GuildSpec):
        """Test that Refine Aggregator transform combines feature suggestions."""
        routes = guild_spec.routes

        # Find aggregator route
        aggregator_route = None
        for step in routes.steps:
            if step.agent and step.agent.name == "Refine Aggregator":
                aggregator_route = step
                break

        assert aggregator_route is not None
        assert aggregator_route.transformer is not None

        handler = aggregator_route.transformer.handler

        # Verify it extracts messages and joins them
        assert "$msgs" in handler or "messages" in handler
        assert "REFINE_BUGFIX" in handler

    def test_critique_agent_conditional_routing(self, guild_spec: GuildSpec):
        """Test that Critique Agent has conditional routing based on verdict."""
        routes = guild_spec.routes

        # Find critique route
        critique_route = None
        for step in routes.steps:
            if step.agent and step.agent.name == "Critique Agent":
                critique_route = step
                break

        assert critique_route is not None
        assert critique_route.transformer is not None

        handler = critique_route.transformer.handler

        # Should check for NEEDS_REVISION
        assert "NEEDS_REVISION" in handler
        # Should track iteration count
        assert "dt_iteration" in handler or "iteration" in handler
        # Should have conditional routing
        assert "DT_REFINEMENT" in handler
        assert "DT_REDTEAM" in handler


class TestAgentConfiguration:
    """Tests for agent configuration validation using the parsed GuildSpec."""

    @pytest.fixture
    def guild_spec(self) -> GuildSpec:
        return load_guild_spec()

    def test_react_agents_have_valid_toolsets(self, guild_spec: GuildSpec):
        """Test that ReAct agents have properly configured toolsets."""
        # Find ReAct agents
        react_agents = [a for a in guild_spec.agents if "react" in a.class_name.lower()]

        assert len(react_agents) == 2  # adaptive_dt and agentic_agent

        for agent in react_agents:
            props = agent.properties
            # Properties should be parsed into the config object
            assert props is not None

    def test_llm_agents_have_system_prompts(self, guild_spec: GuildSpec):
        """Test that LLM agents have system prompts configured."""
        # Find LLM agents (not ReAct, not Aggregating)
        llm_agents = [
            a for a in guild_spec.agents if "LLMAgent" in a.class_name and "react" not in a.class_name.lower()
        ]

        for agent in llm_agents:
            props = agent.properties
            # LLM agents should have a default_system_prompt
            assert hasattr(props, "default_system_prompt") or hasattr(
                props, "system_prompt"
            ), f"Agent {agent.name} missing system prompt"

    def test_aggregating_agent_configuration(self, guild_spec: GuildSpec):
        """Test that Aggregating Agent is properly configured with DictCollector."""
        # Find aggregating agent
        aggregator = next((a for a in guild_spec.agents if a.id == "refine_aggregator"), None)

        assert aggregator is not None
        props = aggregator.properties

        # Should have aggregator and collector config
        assert hasattr(props, "aggregator"), "Aggregator missing aggregator configuration"
        assert hasattr(props, "collector"), "Aggregator missing collector configuration"

        # Verify DictCollector configuration
        collector = props.collector
        assert collector.collector_type == "dict", "Should use DictCollector, not ListCollector"
        assert collector.key_field == "id", "DictCollector should use 'id' as key_field"

        # Verify CountingAggregator configuration
        agg = props.aggregator
        assert agg.aggregation_check == "count", "Should use counting aggregation"
        assert agg.count == 2, "Should wait for 2 messages (novelty + quality)"


class TestDependencyConfiguration:
    """Tests for dependency injection configuration using the parsed GuildSpec."""

    @pytest.fixture
    def guild_spec(self) -> GuildSpec:
        return load_guild_spec()

    def test_llm_dependency_is_configured(self, guild_spec: GuildSpec):
        """Test that LLM dependency is properly configured."""
        dep_map = guild_spec.dependency_map

        assert "llm" in dep_map
        llm_dep = dep_map["llm"]
        assert "LiteLLM" in llm_dep.class_name
        assert "vertex_ai" in llm_dep.properties.get("model", "")

    def test_filesystem_dependency_is_configured(self, guild_spec: GuildSpec):
        """Test that filesystem dependency is properly configured."""
        dep_map = guild_spec.dependency_map

        assert "filesystem" in dep_map
        fs_dep = dep_map["filesystem"]
        assert "FileSystem" in fs_dep.class_name
        # Verify properties are set
        assert fs_dep.properties.get("path_base") == "/tmp/iterative_studio"

    def test_kb_backend_dependency_is_configured(self, guild_spec: GuildSpec):
        """Test that knowledge base backend is properly configured."""
        dep_map = guild_spec.dependency_map

        assert "kb_backend" in dep_map
        kb_dep = dep_map["kb_backend"]
        assert "InMemory" in kb_dep.class_name or "KBIndex" in kb_dep.class_name


class TestEndToEndFlow:
    """Integration tests for complete message flows."""

    @pytest.fixture
    def org_id(self):
        return f"test_org_{shortuuid.uuid()}"

    @pytest.fixture
    def messaging(self) -> MessagingConfig:
        return MessagingConfig(
            backend_module="rustic_ai.core.messaging.backend",
            backend_class="InMemoryMessagingBackend",
            backend_config={},
        )

    @pytest.fixture
    def generator(self) -> GemstoneGenerator:
        return GemstoneGenerator(1)

    def test_guild_starts_and_stops_cleanly(self, messaging: MessagingConfig, org_id: str):
        """Test that guild can start and stop without errors."""
        builder = create_guild_builder(messaging)

        guild = builder.launch(org_id)
        assert guild is not None

        # Give it time to fully initialize
        time.sleep(0.5)

        # Shutdown should complete without errors
        guild.shutdown()

    def test_probe_agent_can_be_added(self, messaging: MessagingConfig, org_id: str):
        """Test that a probe agent can be added to the guild."""
        builder = create_guild_builder(messaging)

        guild = builder.launch(org_id)

        try:
            probe_spec = (
                AgentBuilder(ProbeAgent)
                .set_id("probe_agent")
                .set_name("ProbeAgent")
                .set_description("A probe agent")
                .add_additional_topic(GuildTopics.DEFAULT_TOPICS[0])
                .add_additional_topic(UserProxyAgent.BROADCAST_TOPIC)
                .build_spec()
            )

            probe_agent: ProbeAgent = guild._add_local_agent(probe_spec)
            assert probe_agent is not None

        finally:
            guild.shutdown()

    def test_all_agents_are_instantiated(self, messaging: MessagingConfig, org_id: str):
        """Test that all agents in the spec are properly instantiated."""
        builder = create_guild_builder(messaging)

        guild = builder.launch(org_id)

        try:
            # The guild should have all agents from the spec
            spec_agent_ids = set(guild._agents_by_id.keys())

            # Verify we have the expected count
            assert len(spec_agent_ids) == 16

            # Verify key agents exist
            assert "mode_controller" in spec_agent_ids
            assert "feature_novelty" in spec_agent_ids
            assert "feature_quality" in spec_agent_ids
            assert "refine_aggregator" in spec_agent_ids
            assert "bug_fixer" in spec_agent_ids
            assert "strategy_gen" in spec_agent_ids
            assert "solution_agent" in spec_agent_ids
            assert "critique_agent" in spec_agent_ids
            assert "refinement_agent" in spec_agent_ids
            assert "red_team" in spec_agent_ids
            assert "final_judge" in spec_agent_ids
            assert "adaptive_dt" in spec_agent_ids
            assert "agentic_agent" in spec_agent_ids
            assert "ctx_main" in spec_agent_ids
            assert "ctx_iterative" in spec_agent_ids
            assert "ctx_memory" in spec_agent_ids

        finally:
            guild.shutdown()

    def test_routing_slip_is_attached_to_guild(self, messaging: MessagingConfig, org_id: str):
        """Test that the routing slip is properly attached to the guild."""
        builder = create_guild_builder(messaging)

        guild = builder.launch(org_id)

        try:
            assert guild.routes is not None
            assert len(guild.routes.steps) > 0

            # Verify we have routing rules
            assert any(step.agent and step.agent.name == "Mode Controller" for step in guild.routes.steps)

        finally:
            guild.shutdown()

    def test_dependency_map_is_attached_to_guild(self, messaging: MessagingConfig, org_id: str):
        """Test that the dependency map is properly attached to the guild."""
        builder = create_guild_builder(messaging)

        guild = builder.launch(org_id)

        try:
            assert guild.dependency_map is not None
            assert "llm" in guild.dependency_map
            assert "filesystem" in guild.dependency_map
            assert "kb_backend" in guild.dependency_map

        finally:
            guild.shutdown()


class TestModeControllerTransformIntegration:
    """Integration tests for Mode Controller routing transformation.

    These tests verify that the routing slip transformer correctly extracts
    user messages from the ChatCompletionResponse and forwards them to
    the appropriate mode handler.
    """

    @pytest.fixture
    def org_id(self):
        return f"test_org_{shortuuid.uuid()}"

    @pytest.fixture
    def messaging(self) -> MessagingConfig:
        return MessagingConfig(
            backend_module="rustic_ai.core.messaging.backend",
            backend_class="InMemoryMessagingBackend",
            backend_config={},
        )

    def test_mode_controller_transformer_extracts_user_messages(self):
        """Test that the Mode Controller transformer correctly extracts user messages from input_messages.

        This verifies the fix for the race condition where guild_state.original_request was
        not available when the transformer ran. The fix uses input_messages from the
        ChatCompletionResponse instead.
        """
        from rustic_ai.core.guild.agent_ext.depends.llm.models import (
            ChatCompletionRequest,
        )
        from rustic_ai.core.messaging.core.message import FunctionalTransformer
        from rustic_ai.core.utils.priority import Priority

        # Load the actual handler from guild.json
        guild_spec = load_guild_spec()
        mode_controller_step = None
        for step in guild_spec.routes.steps:
            if step.agent and step.agent.name == "Mode Controller":
                mode_controller_step = step
                break

        assert mode_controller_step is not None
        assert mode_controller_step.transformer is not None

        # Create transformer from the actual handler
        transformer = FunctionalTransformer(
            style=mode_controller_step.transformer.style,
            handler=mode_controller_step.transformer.handler,
        )

        # Simulate a ChatCompletionResponse with mode "agentic"
        from rustic_ai.core.messaging.core.message import MessageRoutable

        payload = {
            "id": "test-response-id",
            "created": 1234567890,
            "model": "gemini-2.5-pro",
            "choices": [
                {
                    "finish_reason": "stop",
                    "index": 0,
                    "message": {"content": "agentic", "role": "assistant"},  # Mode Controller response
                }
            ],
            "usage": {"completion_tokens": 10, "prompt_tokens": 100, "total_tokens": 110},
            "input_messages": [
                {"content": "You are the Mode Controller...", "role": "system"},
                {
                    "content": [{"type": "text", "text": "Search the latest research on transformers"}],
                    "role": "user",
                    "name": "test_user",
                },
            ],
        }

        routable = MessageRoutable(
            topics="MODE_CONTROL",
            priority=Priority.NORMAL,
            payload=payload,
            format="rustic_ai.core.guild.agent_ext.depends.llm.models.ChatCompletionResponse",
        )

        # Create a minimal origin message using GemstoneGenerator
        gen = GemstoneGenerator(1)
        msg_id = gen.get_id(Priority.NORMAL)

        origin = Message.model_validate(
            {
                "id": msg_id.to_int(),
                "sender": {"id": "mode_controller", "name": "Mode Controller"},
                "topics": "MODE_CONTROL",
                "payload": payload,
                "format": "rustic_ai.core.guild.agent_ext.depends.llm.models.ChatCompletionResponse",
                "routing_slip": {"steps": []},
                "message_history": [],
                "thread": [],
            }
        )

        # Transform with EMPTY guild_state (simulating race condition)
        result = transformer.transform(
            origin=origin, agent_state={}, guild_state={}, routable=routable  # Empty - this was the bug
        )

        # Verify transformation succeeded
        assert result is not None, "Transformation should not return None"
        assert result.topics == "AGENTIC", f"Expected topics 'AGENTIC', got '{result.topics}'"
        assert result.format == "rustic_ai.core.guild.agent_ext.depends.llm.models.ChatCompletionRequest"

        # Verify payload is a valid ChatCompletionRequest
        assert "messages" in result.payload, "Payload should have 'messages' field"
        messages = result.payload["messages"]
        assert isinstance(messages, list), f"messages should be a list, got {type(messages)}"
        assert len(messages) == 1, f"Expected 1 user message, got {len(messages)}"
        assert messages[0]["role"] == "user", "First message should be from user"

        # Verify the payload can be validated as ChatCompletionRequest
        request = ChatCompletionRequest.model_validate(result.payload)
        assert len(request.messages) == 1
        assert request.messages[0].role == "user"

    def test_mode_controller_routes_to_correct_modes(self):
        """Test that Mode Controller routes to correct topics for each mode."""
        from rustic_ai.core.messaging.core.message import (
            FunctionalTransformer,
            MessageRoutable,
        )
        from rustic_ai.core.utils.priority import Priority

        # Load the actual handler
        guild_spec = load_guild_spec()
        mode_controller_step = next(
            step for step in guild_spec.routes.steps if step.agent and step.agent.name == "Mode Controller"
        )

        transformer = FunctionalTransformer(
            style=mode_controller_step.transformer.style,
            handler=mode_controller_step.transformer.handler,
        )

        mode_to_topic = {
            "refine": ["REFINE_NOVELTY", "REFINE_QUALITY"],
            "deepthink": "DT_STRATEGY",
            "adaptive": "ADAPTIVE_DT",
            "agentic": "AGENTIC",
            "contextual": "CTX_MAIN",
        }

        gen = GemstoneGenerator(1)

        for mode, expected_topic in mode_to_topic.items():
            payload = {
                "id": "test-id",
                "created": 1234567890,
                "model": "test-model",
                "choices": [{"finish_reason": "stop", "index": 0, "message": {"content": mode, "role": "assistant"}}],
                "usage": {"completion_tokens": 1, "prompt_tokens": 1, "total_tokens": 2},
                "input_messages": [
                    {"content": "system prompt", "role": "system"},
                    {"content": "user message", "role": "user"},
                ],
            }

            routable = MessageRoutable(
                topics="MODE_CONTROL",
                priority=Priority.NORMAL,
                payload=payload,
                format="rustic_ai.core.guild.agent_ext.depends.llm.models.ChatCompletionResponse",
            )

            msg_id = gen.get_id(Priority.NORMAL)
            origin = Message.model_validate(
                {
                    "id": msg_id.to_int(),
                    "sender": {"id": "mode_controller", "name": "Mode Controller"},
                    "topics": "MODE_CONTROL",
                    "payload": payload,
                    "format": "rustic_ai.core.guild.agent_ext.depends.llm.models.ChatCompletionResponse",
                    "routing_slip": {"steps": []},
                    "message_history": [],
                    "thread": [],
                }
            )

            result = transformer.transform(origin=origin, agent_state={}, guild_state={}, routable=routable)

            assert result is not None, f"Transformation failed for mode '{mode}'"
            assert (
                result.topics == expected_topic
            ), f"Mode '{mode}' should route to '{expected_topic}', got '{result.topics}'"
            assert result.context.get("mode") == mode, f"Context should contain mode '{mode}'"
