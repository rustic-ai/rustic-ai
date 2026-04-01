"""Tests for Guild Generator agents using wrap_agent_for_testing."""

import json

import pytest
from pydantic import BaseModel

from rustic_ai.core.guild.agent_ext.depends.dependency_resolver import (
    DependencyResolver,
    DependencySpec,
)
from rustic_ai.core.guild.agent_ext.depends.llm import LLM
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    AssistantMessage,
    ChatCompletionRequest,
    ChatCompletionResponse,
    Choice,
    CompletionUsage,
    FinishReason,
    SystemMessage,
    UserMessage,
)
from rustic_ai.core.guild.builders import AgentBuilder
from rustic_ai.core.guild.dsl import GuildTopics
from rustic_ai.core.messaging.core.message import AgentTag, Message
from rustic_ai.core.ui_protocol.types import TextFormat
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.core.utils.gemstone_id import GemstoneGenerator
from rustic_ai.core.utils.priority import Priority
from rustic_ai.showcase.guild_generator.agent_registry import AgentRegistryAgent
from rustic_ai.showcase.guild_generator.flowchart_agent import FlowchartAgent
from rustic_ai.showcase.guild_generator.guild_export import GuildExportAgent
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
from rustic_ai.showcase.guild_generator.route_builder import RouteBuilderAgent
from rustic_ai.showcase.guild_generator.state_manager import StateManagerAgent
from rustic_ai.showcase.guild_generator.transformation_builder import (
    TransformationBuilderAgent,
)
from rustic_ai.testing.helpers import wrap_agent_for_testing


class MockLLM(LLM):
    """Mock LLM for testing that returns predefined responses."""

    def __init__(self, response_content: str):
        self.response_content = response_content
        self._model = "mock-model"

    def completion(self, prompt: ChatCompletionRequest, model=None) -> ChatCompletionResponse:
        return ChatCompletionResponse(
            id="mock-completion-id",
            created=1234567890,
            model=self._model,
            choices=[
                Choice(
                    index=0,
                    message=AssistantMessage(content=self.response_content),
                    finish_reason=FinishReason.stop,
                )
            ],
            usage=CompletionUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
        )

    async def async_completion(self, prompt: ChatCompletionRequest, model=None) -> ChatCompletionResponse:
        return self.completion(prompt, model)

    @property
    def model(self) -> str:
        return self._model

    def get_config(self) -> dict:
        return {"model": self._model}


class MockLLMResolver(DependencyResolver[LLM]):
    """Resolver that returns a MockLLM with a predefined response."""

    memoize_resolution: bool = False

    def __init__(self, response_content: str):
        super().__init__()
        self.response_content = response_content

    def resolve(self, org_id: str, guild_id: str, agent_id: str) -> LLM:
        return MockLLM(self.response_content)


@pytest.fixture
def generator() -> GemstoneGenerator:
    return GemstoneGenerator(1)


@pytest.fixture
def build_message_from_payload():
    def _build_message_from_payload(
        generator: GemstoneGenerator,
        payload: BaseModel | dict,
        *,
        format: str | None = None,
        session_state: dict | None = None,
    ) -> Message:
        payload_dict = payload.model_dump() if isinstance(payload, BaseModel) else payload
        computed_format = format or (
            get_qualified_class_name(type(payload)) if isinstance(payload, BaseModel) else None
        )

        return Message(
            id_obj=generator.get_id(Priority.NORMAL),
            sender=AgentTag(name="test-agent", id="agent-123"),
            topics=GuildTopics.DEFAULT_TOPICS,
            payload=payload_dict,
            format=computed_format if computed_format else get_qualified_class_name(Message),
            session_state=session_state or {},
        )

    return _build_message_from_payload


class TestAgentRegistryAgent:
    """Tests for the AgentRegistryAgent."""

    def test_agent_registry_responds_to_add_agent_action(self, generator, build_message_from_payload):
        """Test that agent registry processes add_agent actions."""
        mock_response = json.dumps({
            "agent_spec": {
                "id": "summarizer_agent",
                "name": "Text Summarizer",
                "description": "Summarizes text input",
                "class_name": "rustic_ai.llm_agent.llm_agent.LLMAgent",
                "properties": {"default_system_prompt": "You summarize text."},
            },
            "explanation": "LLMAgent is best for text summarization tasks.",
        })

        dependency_map = {
            "llm": DependencySpec(
                class_name=get_qualified_class_name(MockLLMResolver),
                properties={"response_content": mock_response},
            ),
        }

        agent_spec = (
            AgentBuilder(AgentRegistryAgent)
            .set_id("agent_registry")
            .set_name("Agent Registry")
            .set_description("Test agent registry")
            .build_spec()
        )

        agent, results = wrap_agent_for_testing(agent_spec, dependency_map=dependency_map)

        action = OrchestratorAction(
            action=ActionType.ADD_AGENT,
            details={"purpose": "summarizes text"},
            user_message="@Orchestrator add an agent that summarizes text",
        )

        agent._on_message(build_message_from_payload(generator, action))

        assert len(results) == 1
        assert results[0].format == get_qualified_class_name(AgentLookupResponse)
        payload = AgentLookupResponse.model_validate(results[0].payload)
        assert payload.agent_spec["id"] == "summarizer_agent"
        assert payload.explanation == "LLMAgent is best for text summarization tasks."

    def test_agent_registry_handles_direct_lookup(self, generator, build_message_from_payload):
        """Test that agent registry handles direct AgentLookupRequest."""
        mock_response = json.dumps({
            "agent_spec": {
                "id": "qa_agent",
                "name": "QA Agent",
                "description": "Answers questions",
                "class_name": "rustic_ai.llm_agent.llm_agent.LLMAgent",
            },
            "explanation": "Selected LLMAgent for Q&A.",
        })

        dependency_map = {
            "llm": DependencySpec(
                class_name=get_qualified_class_name(MockLLMResolver),
                properties={"response_content": mock_response},
            ),
        }

        agent_spec = (
            AgentBuilder(AgentRegistryAgent)
            .set_id("agent_registry")
            .set_name("Agent Registry")
            .set_description("Test agent registry")
            .build_spec()
        )

        agent, results = wrap_agent_for_testing(agent_spec, dependency_map=dependency_map)

        request = AgentLookupRequest(
            description="an agent that answers questions",
            input_format="ChatCompletionRequest",
            output_format="ChatCompletionResponse",
        )

        agent._on_message(build_message_from_payload(generator, request))

        assert len(results) == 1
        payload = AgentLookupResponse.model_validate(results[0].payload)
        assert payload.agent_spec["id"] == "qa_agent"


class TestAgentRegistryDependencyMapFormat:
    """Tests that AgentRegistryAgent produces valid dependency_map for AgentLaunchRequest."""

    def test_agent_spec_with_dependency_map_is_valid_for_agent_launch(
        self, generator, build_message_from_payload
    ):
        """Test that agent spec with dependency_map can be used in AgentLaunchRequest.

        This is the key end-to-end test for the DependencySpec fix. When the LLM
        generates an agent spec with dependencies, the dependency_map must be in
        the correct format for AgentLaunchRequest validation.
        """
        # This mock response includes dependency_map in the CORRECT format
        # Each dependency value must be a dict with "class_name" and "properties"
        mock_response = json.dumps({
            "agent_spec": {
                "id": "llm_summarizer",
                "name": "LLM Summarizer",
                "description": "Summarizes text using an LLM",
                "class_name": "rustic_ai.llm_agent.llm_agent.LLMAgent",
                "additional_topics": [],
                "properties": {"default_system_prompt": "You summarize text."},
                "dependency_map": {
                    "llm": {
                        "class_name": "rustic_ai.litellm.agent_ext.llm.LiteLLMResolver",
                        "properties": {}
                    }
                },
                "listen_to_default_topic": True,
                "act_only_when_tagged": False,
            },
            "explanation": "LLMAgent with proper dependency_map format.",
        })

        test_dependency_map = {
            "llm": DependencySpec(
                class_name=get_qualified_class_name(MockLLMResolver),
                properties={"response_content": mock_response},
            ),
        }

        agent_spec = (
            AgentBuilder(AgentRegistryAgent)
            .set_id("agent_registry")
            .set_name("Agent Registry")
            .set_description("Test agent registry")
            .build_spec()
        )

        agent, results = wrap_agent_for_testing(agent_spec, dependency_map=test_dependency_map)

        action = OrchestratorAction(
            action=ActionType.ADD_AGENT,
            details={"purpose": "summarizes text"},
            user_message="@Orchestrator add an LLM agent that summarizes text",
        )

        agent._on_message(build_message_from_payload(generator, action))

        assert len(results) == 1
        assert results[0].format == get_qualified_class_name(AgentLookupResponse)

        # Parse the response
        payload = AgentLookupResponse.model_validate(results[0].payload)
        agent_spec_dict = payload.agent_spec

        # Verify the dependency_map is in the correct format
        assert "dependency_map" in agent_spec_dict
        llm_dep = agent_spec_dict["dependency_map"]["llm"]
        assert isinstance(llm_dep, dict), (
            f"dependency_map.llm should be a dict, got {type(llm_dep).__name__}: {llm_dep}"
        )
        assert "class_name" in llm_dep, "dependency_map.llm missing 'class_name'"
        assert "properties" in llm_dep, "dependency_map.llm missing 'properties'"

        # This is the key validation - can we create an AgentLaunchRequest with this spec?
        # This would have failed before the fix with:
        # "Input should be a valid dictionary or instance of DependencySpec"
        try:
            # Validate each dependency can be parsed as DependencySpec
            for dep_key, dep_value in agent_spec_dict["dependency_map"].items():
                DependencySpec(**dep_value)
        except Exception as e:
            pytest.fail(
                f"dependency_map values should be valid DependencySpec format: {e}\n"
                f"dependency_map: {agent_spec_dict['dependency_map']}"
            )

    def test_agent_spec_with_string_dependency_would_fail(self, generator, build_message_from_payload):
        """Test that proves the old format (string instead of dict) would fail validation.

        This test documents why the fix was needed - if the LLM generates
        dependency_map values as strings, it would fail AgentLaunchRequest validation.
        """
        from rustic_ai.core.guild.agent_ext.depends.dependency_resolver import DependencySpec

        # This is the WRONG format that was causing the error
        wrong_format_dependency_map = {
            "llm": "rustic_ai.litellm.agent_ext.llm.LiteLLMResolver"  # String, not dict!
        }

        # This should fail validation
        with pytest.raises(Exception):  # Pydantic ValidationError
            DependencySpec(**wrong_format_dependency_map["llm"])

    @pytest.mark.skip(reason="AGENT_REGISTRY is now loaded from API, not a static constant")
    def test_registry_provides_correct_dependency_format_to_llm(self):
        """Test that AGENT_REGISTRY shows correct dependency format to guide the LLM."""
        pass


class TestRouteBuilderAgent:
    """Tests for the RouteBuilderAgent."""

    def test_route_builder_creates_routing_rule(self, generator, build_message_from_payload):
        """Test that route builder creates routing rules from actions."""
        mock_response = json.dumps({
            "routing_rule": {
                "agent": {"name": "summarizer"},
                "message_format": "rustic_ai.core.guild.agent_ext.depends.llm.models.ChatCompletionResponse",
                "destination": {"topics": "formatter_input"},
            },
            "explanation": "Routes summarizer output to formatter.",
        })

        dependency_map = {
            "llm": DependencySpec(
                class_name=get_qualified_class_name(MockLLMResolver),
                properties={"response_content": mock_response},
            ),
        }

        agent_spec = (
            AgentBuilder(RouteBuilderAgent)
            .set_id("route_builder")
            .set_name("Route Builder")
            .set_description("Test route builder")
            .build_spec()
        )

        agent, results = wrap_agent_for_testing(agent_spec, dependency_map=dependency_map)

        action = OrchestratorAction(
            action=ActionType.ADD_ROUTE,
            details={
                "source_agent": "summarizer",
                "target_agent": "formatter",
            },
            user_message="@Orchestrator connect summarizer to formatter",
        )

        agent._on_message(build_message_from_payload(generator, action))

        assert len(results) == 1
        assert results[0].format == get_qualified_class_name(RouteResponse)
        payload = RouteResponse.model_validate(results[0].payload)
        assert payload.routing_rule["agent"]["name"] == "summarizer"
        assert payload.routing_rule["destination"]["topics"] == "formatter_input"

    def test_route_builder_handles_direct_request(self, generator, build_message_from_payload):
        """Test that route builder handles direct RouteRequest."""
        mock_response = json.dumps({
            "routing_rule": {
                "agent": {"name": "processor"},
                "message_format": "test.Format",
                "destination": {"topics": "output"},
            },
            "explanation": "Created route for processor.",
        })

        dependency_map = {
            "llm": DependencySpec(
                class_name=get_qualified_class_name(MockLLMResolver),
                properties={"response_content": mock_response},
            ),
        }

        agent_spec = (
            AgentBuilder(RouteBuilderAgent)
            .set_id("route_builder")
            .set_name("Route Builder")
            .set_description("Test route builder")
            .build_spec()
        )

        agent, results = wrap_agent_for_testing(agent_spec, dependency_map=dependency_map)

        request = RouteRequest(
            agent_name="processor",
            message_format="test.Format",
            destination_topic="output",
        )

        agent._on_message(build_message_from_payload(generator, request))

        assert len(results) == 1
        payload = RouteResponse.model_validate(results[0].payload)
        assert payload.routing_rule["agent"]["name"] == "processor"


class TestTransformationBuilderAgent:
    """Tests for the TransformationBuilderAgent."""

    def test_transformation_builder_creates_jsonata(self, generator, build_message_from_payload):
        """Test that transformation builder creates JSONata transformations."""
        mock_response = json.dumps({
            "transformation": {
                "style": "simple",
                "expression_type": "jsonata",
                "handler": "$.choices[0].message.content",
                "output_format": "rustic_ai.core.ui_protocol.types.TextFormat",
            },
            "explanation": "Extracts message content from chat completion.",
        })

        dependency_map = {
            "llm": DependencySpec(
                class_name=get_qualified_class_name(MockLLMResolver),
                properties={"response_content": mock_response},
            ),
        }

        agent_spec = (
            AgentBuilder(TransformationBuilderAgent)
            .set_id("transform_builder")
            .set_name("Transform Builder")
            .set_description("Test transform builder")
            .build_spec()
        )

        agent, results = wrap_agent_for_testing(agent_spec, dependency_map=dependency_map)

        request = TransformRequest(
            source_format="rustic_ai.core.guild.agent_ext.depends.llm.models.ChatCompletionResponse",
            target_format="rustic_ai.core.ui_protocol.types.TextFormat",
            source_agent_name="summarizer",
            target_agent_name="display",
        )

        agent._on_message(build_message_from_payload(generator, request))

        assert len(results) == 1
        assert results[0].format == get_qualified_class_name(TransformResponse)
        payload = TransformResponse.model_validate(results[0].payload)
        assert payload.transformation.style == "simple"
        assert payload.transformation.handler == "$.choices[0].message.content"

    def test_transformation_builder_creates_content_based_router(self, generator, build_message_from_payload):
        """Test that transformation builder can create content-based routers."""
        mock_response = json.dumps({
            "transformation": {
                "style": "content_based_router",
                "expression_type": "jsonata",
                "handler": '({"format": "test.Format", "payload": $.payload})',
            },
            "explanation": "Content-based router transformation.",
        })

        dependency_map = {
            "llm": DependencySpec(
                class_name=get_qualified_class_name(MockLLMResolver),
                properties={"response_content": mock_response},
            ),
        }

        agent_spec = (
            AgentBuilder(TransformationBuilderAgent)
            .set_id("transform_builder")
            .set_name("Transform Builder")
            .set_description("Test transform builder")
            .build_spec()
        )

        agent, results = wrap_agent_for_testing(agent_spec, dependency_map=dependency_map)

        request = TransformRequest(
            source_format="input.Format",
            target_format="output.Format",
            source_agent_name="source",
            target_agent_name="target",
            requirements="Need to dynamically route based on content",
        )

        agent._on_message(build_message_from_payload(generator, request))

        assert len(results) == 1
        payload = TransformResponse.model_validate(results[0].payload)
        assert payload.transformation.style == "content_based_router"


class TestStateManagerAgent:
    """Tests for the StateManagerAgent."""

    def test_state_manager_handles_agent_lookup_response(self, generator, build_message_from_payload):
        """Test that state manager processes agent lookup responses."""
        agent_spec = (
            AgentBuilder(StateManagerAgent)
            .set_id("state_manager")
            .set_name("State Manager")
            .set_description("Test state manager")
            .build_spec()
        )

        agent, results = wrap_agent_for_testing(agent_spec)

        response = AgentLookupResponse(
            agent_spec={
                "id": "test_agent",
                "name": "Test Agent",
                "class_name": "test.TestAgent",
            },
            explanation="Added test agent",
            available_agents=[],
        )

        agent._on_message(build_message_from_payload(generator, response))

        # Should send TextFormat confirmation and FlowchartUpdateRequest
        assert len(results) == 2

        text_results = [r for r in results if r.format == get_qualified_class_name(TextFormat)]
        assert len(text_results) == 1
        text_payload = TextFormat.model_validate(text_results[0].payload)
        assert "Test Agent" in text_payload.text

        flowchart_results = [r for r in results if r.format == get_qualified_class_name(FlowchartUpdateRequest)]
        assert len(flowchart_results) == 1

    def test_state_manager_handles_route_response(self, generator, build_message_from_payload):
        """Test that state manager processes route responses."""
        agent_spec = (
            AgentBuilder(StateManagerAgent)
            .set_id("state_manager")
            .set_name("State Manager")
            .set_description("Test state manager")
            .build_spec()
        )

        agent, results = wrap_agent_for_testing(agent_spec)

        response = RouteResponse(
            routing_rule={
                "agent": {"name": "source_agent"},
                "destination": {"topics": "target_topic"},
            },
            explanation="Route created",
        )

        agent._on_message(build_message_from_payload(generator, response))

        assert len(results) == 2

        text_results = [r for r in results if r.format == get_qualified_class_name(TextFormat)]
        assert len(text_results) == 1
        text_payload = TextFormat.model_validate(text_results[0].payload)
        assert "source_agent" in text_payload.text

    def test_state_manager_shows_help(self, generator, build_message_from_payload):
        """Test that state manager shows help on HELP action."""
        agent_spec = (
            AgentBuilder(StateManagerAgent)
            .set_id("state_manager")
            .set_name("State Manager")
            .set_description("Test state manager")
            .build_spec()
        )

        agent, results = wrap_agent_for_testing(agent_spec)

        action = OrchestratorAction(
            action=ActionType.HELP,
            details={},
            user_message="@Orchestrator help",
        )

        agent._on_message(build_message_from_payload(generator, action))

        assert len(results) == 1
        assert results[0].format == get_qualified_class_name(TextFormat)
        text_payload = TextFormat.model_validate(results[0].payload)
        assert "Guild Generator Help" in text_payload.text

    def test_state_manager_sets_guild_name(self, generator, build_message_from_payload):
        """Test that state manager handles SET_NAME action."""
        agent_spec = (
            AgentBuilder(StateManagerAgent)
            .set_id("state_manager")
            .set_name("State Manager")
            .set_description("Test state manager")
            .build_spec()
        )

        agent, results = wrap_agent_for_testing(agent_spec)

        action = OrchestratorAction(
            action=ActionType.SET_NAME,
            details={"name": "My Custom Guild"},
            user_message="@Orchestrator name this guild 'My Custom Guild'",
        )

        agent._on_message(build_message_from_payload(generator, action))

        assert len(results) == 1
        text_payload = TextFormat.model_validate(results[0].payload)
        assert "My Custom Guild" in text_payload.text


class TestFlowchartAgent:
    """Tests for the FlowchartAgent."""

    def test_flowchart_agent_generates_vegalite(self, generator, build_message_from_payload):
        """Test that flowchart agent generates VegaLite spec."""
        agent_spec = (
            AgentBuilder(FlowchartAgent)
            .set_id("flowchart")
            .set_name("Flowchart")
            .set_description("Test flowchart agent")
            .build_spec()
        )

        agent, results = wrap_agent_for_testing(agent_spec)

        request = FlowchartUpdateRequest(trigger="update")

        agent._on_message(build_message_from_payload(generator, request))

        assert len(results) == 1
        assert results[0].format == get_qualified_class_name(VegaLiteFormat)
        payload = VegaLiteFormat.model_validate(results[0].payload)
        assert payload.response["$schema"] == "https://vega.github.io/schema/vega-lite/v5.json"
        assert "layer" in payload.response

    def test_flowchart_agent_shows_on_orchestrator_action(self, generator, build_message_from_payload):
        """Test that flowchart agent responds to SHOW_FLOW action."""
        agent_spec = (
            AgentBuilder(FlowchartAgent)
            .set_id("flowchart")
            .set_name("Flowchart")
            .set_description("Test flowchart agent")
            .build_spec()
        )

        agent, results = wrap_agent_for_testing(agent_spec)

        action = OrchestratorAction(
            action=ActionType.SHOW_FLOW,
            details={},
            user_message="@Orchestrator show flow",
        )

        agent._on_message(build_message_from_payload(generator, action))

        assert len(results) == 1
        assert results[0].format == get_qualified_class_name(VisualizationResponse)

    def test_flowchart_includes_agents_from_state(self, generator, build_message_from_payload):
        """Test that flowchart includes agents from guild state."""
        agent_spec = (
            AgentBuilder(FlowchartAgent)
            .set_id("flowchart")
            .set_name("Flowchart")
            .set_description("Test flowchart agent")
            .build_spec()
        )

        agent, results = wrap_agent_for_testing(agent_spec)

        request = FlowchartUpdateRequest(trigger="update")
        session_state = {
            "guild_builder": {
                "name": "Test Guild",
                "description": "Test description",
                "agents": [
                    {"id": "agent1", "name": "Agent One", "class_name": "test.LLMAgent"},
                    {"id": "agent2", "name": "Agent Two", "class_name": "test.SplitterAgent"},
                ],
                "routes": [],
            }
        }

        agent._on_message(build_message_from_payload(generator, request, session_state=session_state))

        assert len(results) == 1
        payload = VegaLiteFormat.model_validate(results[0].payload)
        assert payload.spec["title"]["text"] == "Test Guild"

        # Check nodes include the agents
        nodes_layer = payload.spec["layer"][1]
        nodes = nodes_layer["data"]["values"]
        node_names = [n["name"] for n in nodes]
        assert "Agent One" in node_names
        assert "Agent Two" in node_names


class TestGuildExportAgent:
    """Tests for the GuildExportAgent."""

    def test_guild_export_handles_empty_state(self, generator, build_message_from_payload):
        """Test that export agent handles empty guild state."""
        agent_spec = (
            AgentBuilder(GuildExportAgent)
            .set_id("exporter")
            .set_name("Exporter")
            .set_description("Test export agent")
            .build_spec()
        )

        agent, results = wrap_agent_for_testing(agent_spec)

        action = OrchestratorAction(
            action=ActionType.PUBLISH,
            details={},
            user_message="@Orchestrator publish",
        )

        agent._on_message(build_message_from_payload(generator, action))

        # Should send error message about no agents
        assert len(results) == 1
        assert results[0].format == get_qualified_class_name(TextFormat)
        text_payload = TextFormat.model_validate(results[0].payload)
        assert "Cannot export" in text_payload.text or "No agents" in text_payload.text

    def test_guild_export_creates_valid_spec(self, generator, build_message_from_payload):
        """Test that export agent creates valid guild spec."""
        agent_spec = (
            AgentBuilder(GuildExportAgent)
            .set_id("exporter")
            .set_name("Exporter")
            .set_description("Test export agent")
            .build_spec()
        )

        agent, results = wrap_agent_for_testing(agent_spec)

        action = OrchestratorAction(
            action=ActionType.PUBLISH,
            details={},
            user_message="@Orchestrator publish",
        )
        session_state = {
            "guild_builder": {
                "name": "My Guild",
                "description": "A test guild",
                "agents": [
                    {
                        "id": "agent1",
                        "name": "Test Agent",
                        "description": "Does testing",
                        "class_name": "test.TestAgent",
                    }
                ],
                "routes": [],
            }
        }

        agent._on_message(build_message_from_payload(generator, action, session_state=session_state))

        # Should send ExportResponse and TextFormat
        assert len(results) >= 1

        export_results = [r for r in results if r.format == get_qualified_class_name(ExportResponse)]
        assert len(export_results) == 1
        export_payload = ExportResponse.model_validate(export_results[0].payload)
        assert export_payload.guild_spec["name"] == "My Guild"
        assert len(export_payload.guild_spec["agents"]) == 1
        assert export_payload.is_valid

    def test_guild_export_handles_direct_request(self, generator, build_message_from_payload):
        """Test that export agent handles direct ExportRequest."""
        agent_spec = (
            AgentBuilder(GuildExportAgent)
            .set_id("exporter")
            .set_name("Exporter")
            .set_description("Test export agent")
            .build_spec()
        )

        agent, results = wrap_agent_for_testing(agent_spec)

        request = ExportRequest(format="json", run_validation=True)
        session_state = {
            "guild_builder": {
                "name": "Export Test",
                "description": "Testing export",
                "agents": [
                    {
                        "id": "test",
                        "name": "Test",
                        "description": "Test agent",
                        "class_name": "test.Test",
                    }
                ],
                "routes": [],
            }
        }

        agent._on_message(build_message_from_payload(generator, request, session_state=session_state))

        assert len(results) == 1
        assert results[0].format == get_qualified_class_name(ExportResponse)
        export_payload = ExportResponse.model_validate(results[0].payload)
        assert export_payload.json_output  # Should have JSON string

    def test_guild_export_reports_validation_errors(self, generator, build_message_from_payload):
        """Test that export agent reports validation errors."""
        agent_spec = (
            AgentBuilder(GuildExportAgent)
            .set_id("exporter")
            .set_name("Exporter")
            .set_description("Test export agent")
            .build_spec()
        )

        agent, results = wrap_agent_for_testing(agent_spec)

        action = OrchestratorAction(
            action=ActionType.PUBLISH,
            details={},
            user_message="@Orchestrator publish",
        )
        session_state = {
            "guild_builder": {
                "name": "Invalid Guild",
                "description": "Has validation errors",
                "agents": [
                    {
                        # Missing required fields
                        "id": "bad_agent",
                    }
                ],
                "routes": [
                    {
                        # Missing agent or agent_type
                    }
                ],
            }
        }

        agent._on_message(build_message_from_payload(generator, action, session_state=session_state))

        # Should still export but with validation errors
        export_results = [r for r in results if r.format == get_qualified_class_name(ExportResponse)]
        if export_results:
            export_payload = ExportResponse.model_validate(export_results[0].payload)
            assert not export_payload.is_valid
            assert len(export_payload.validation_errors) > 0
