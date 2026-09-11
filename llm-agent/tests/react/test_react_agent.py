import json
from typing import Any, ClassVar, List, Optional
from unittest.mock import patch

import httpx
import openai
from pydantic import BaseModel, ConfigDict, ValidationError
import pytest

from rustic_ai.core.guild.agent_ext.depends.dependency_resolver import DependencySpec
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    AssistantMessage,
    ChatCompletionError,
    ChatCompletionMessageToolCall,
    ChatCompletionRequest,
    ChatCompletionResponse,
    Choice,
    CompletionUsage,
    FinishReason,
    FunctionCall,
    ResponseCodes,
    SystemMessage,
    ToolType,
    UserMessage,
)
from rustic_ai.core.guild.agent_ext.depends.llm.tools_manager import ToolSpec
from rustic_ai.core.guild.builders import AgentBuilder
from rustic_ai.core.guild.dsl import AgentSpec
from rustic_ai.llm_agent.react import (
    DEFAULT_REACT_SYSTEM_PROMPT,
    CompositeToolset,
    DuckDuckGoInstantAnswerToolset,
    MathToolset,
    MediaWikiSearchToolset,
    ReActAgent,
    ReActAgentConfig,
    ReActSkillSpec,
    ReActStep,
    ReActToolOutcome,
    ReActToolset,
    TemporalToolset,
    ToolOutcomeDisposition,
)

from rustic_ai.testing.helpers import wrap_agent_for_testing


# Test tool parameter models
class CalculateParams(BaseModel):
    """Parameters for calculate tool."""

    expression: str


class SearchParams(BaseModel):
    """Parameters for search tool."""

    query: str


class StrictParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    count: int


def test_default_prompt_is_short_and_tool_agnostic():
    assert len(DEFAULT_REACT_SYSTEM_PROMPT.split()) < 120
    assert "dependent steps" in DEFAULT_REACT_SYSTEM_PROMPT
    assert "never repeat identical arguments" in DEFAULT_REACT_SYSTEM_PROMPT
    assert "calculate" not in DEFAULT_REACT_SYSTEM_PROMPT
    assert "mediawiki" not in DEFAULT_REACT_SYSTEM_PROMPT


def test_validation_error_message_is_compact():
    with pytest.raises(ValidationError) as exc_info:
        StrictParams.model_validate({"count": "not-an-integer", "extra": True})

    message = ReActAgent._validation_error_message(exc_info.value)

    assert message.startswith("Invalid tool arguments: ")
    assert "count:" in message
    assert "extra:" in message
    assert "input_value" not in message
    assert "https://" not in message


# Test toolset implementation
class CalculatorToolset(ReActToolset):
    """A simple calculator toolset for testing."""

    def get_toolspecs(self) -> List[ToolSpec]:
        return [
            ToolSpec(
                name="calculate",
                description="Evaluate a mathematical expression",
                parameter_class=CalculateParams,
            )
        ]

    def execute(self, tool_name: str, args: Any) -> str:
        if tool_name == "calculate":
            assert isinstance(args, CalculateParams)
            # Safe evaluation for testing
            try:
                result = eval(args.expression)  # noqa: S307
                return str(result)
            except Exception as e:
                return f"Error: {e}"
        raise ValueError(f"Unknown tool: {tool_name}")


class SearchToolset(ReActToolset):
    """A mock search toolset for testing."""

    def get_toolspecs(self) -> List[ToolSpec]:
        return [
            ToolSpec(
                name="search",
                description="Search for information",
                parameter_class=SearchParams,
            )
        ]

    def execute(self, tool_name: str, args: Any) -> str:
        if tool_name == "search":
            assert isinstance(args, SearchParams)
            return f"Search results for: {args.query}"
        raise ValueError(f"Unknown tool: {tool_name}")


class BrokenSkillToolset(CalculatorToolset):
    def get_skill_specs(self) -> List[ReActSkillSpec]:
        return [
            ReActSkillSpec(
                name="broken",
                description="References a tool this toolset does not own.",
                tool_names=["missing_tool"],
            )
        ]


class PartiallySkilledToolset(ReActToolset):
    def get_toolspecs(self) -> List[ToolSpec]:
        return CalculatorToolset().get_toolspecs() + SearchToolset().get_toolspecs()

    def get_skill_specs(self) -> List[ReActSkillSpec]:
        return [
            ReActSkillSpec(
                name="arithmetic",
                description="Arithmetic only.",
                tool_names=["calculate"],
            )
        ]

    def execute(self, tool_name: str, args: BaseModel) -> str:
        raise NotImplementedError


class SiblingClaimingToolset(SearchToolset):
    def get_skill_specs(self) -> List[ReActSkillSpec]:
        return [
            ReActSkillSpec(
                name="bad_search",
                description="Incorrectly claims another child tool.",
                tool_names=["calculate"],
            )
        ]


class ConflictingSharedSkillToolset(SearchToolset):
    def get_skill_specs(self) -> List[ReActSkillSpec]:
        return [
            ReActSkillSpec(
                name="math_and_units",
                description="A conflicting description.",
                tool_names=["search"],
            )
        ]


class CountingMathToolset(MathToolset):
    execution_count: ClassVar[int] = 0

    def execute(self, tool_name: str, args: BaseModel) -> str:
        type(self).execution_count += 1
        return super().execute(tool_name, args)


class FixedLookupToolset(ReActToolset):
    outcomes: ClassVar[List[str]] = ["no_result"]
    execution_count: ClassVar[int] = 0

    def get_toolspecs(self) -> List[ToolSpec]:
        return [
            ToolSpec(
                name="duckduckgo_instant_answer",
                description="Look up a concise entity or topic.",
                parameter_class=SearchParams,
            )
        ]

    def execute(self, tool_name: str, args: BaseModel) -> str:
        index = min(type(self).execution_count, len(type(self).outcomes) - 1)
        type(self).execution_count += 1
        status = type(self).outcomes[index]
        if status == "ok":
            return json.dumps(
                {
                    "status": "ok",
                    "abstract": {"text": "Paris is the capital of France."},
                }
            )
        return json.dumps({"status": "no_result", "query": getattr(args, "query", "")})

    def interpret_result(self, tool_name: str, args: BaseModel, result: str) -> Optional[ReActToolOutcome]:
        payload = json.loads(result)
        if payload["status"] == "ok":
            return ReActToolOutcome(
                disposition=ToolOutcomeDisposition.SUCCESS,
                verified_summary=payload["abstract"]["text"],
            )
        return ReActToolOutcome(
            disposition=ToolOutcomeDisposition.NO_RESULT,
            code="no_result",
            message="The lookup could not verify this fact.",
        )


def create_mock_response(
    content: str,
    tool_calls: Optional[List[ChatCompletionMessageToolCall]] = None,
    finish_reason: FinishReason = FinishReason.stop,
) -> ChatCompletionResponse:
    """Helper to create mock LLM responses."""
    return ChatCompletionResponse(
        id="chatcmpl-test",
        created=1234567890,
        model="test-model",
        choices=[
            Choice(
                index=0,
                message=AssistantMessage(
                    content=content,
                    tool_calls=tool_calls,
                ),
                finish_reason=finish_reason,
            )
        ],
        usage=CompletionUsage(
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
        ),
    )


def create_tool_call(
    tool_id: str,
    name: str,
    arguments: dict,
) -> ChatCompletionMessageToolCall:
    """Helper to create tool call objects."""
    return ChatCompletionMessageToolCall(
        id=tool_id,
        type=ToolType.function,
        function=FunctionCall(
            name=name,
            arguments=json.dumps(arguments),
        ),
    )


class TestReActToolset:
    """Tests for ReActToolset and related classes."""

    def test_calculator_toolset_specs(self):
        """Test that CalculatorToolset returns correct tool specs."""
        toolset = CalculatorToolset()
        specs = toolset.get_toolspecs()

        assert len(specs) == 1
        assert specs[0].name == "calculate"
        assert specs[0].description == "Evaluate a mathematical expression"

    def test_calculator_toolset_execute(self):
        """Test that CalculatorToolset executes correctly."""
        toolset = CalculatorToolset()
        args = CalculateParams(expression="2 + 2")
        result = toolset.execute("calculate", args)

        assert result == "4"

    def test_calculator_toolset_execute_complex(self):
        """Test complex calculations."""
        toolset = CalculatorToolset()
        args = CalculateParams(expression="10 * 5 + 3")
        result = toolset.execute("calculate", args)

        assert result == "53"

    def test_toolset_unknown_tool(self):
        """Test that unknown tool raises ValueError."""
        toolset = CalculatorToolset()
        args = CalculateParams(expression="2 + 2")

        with pytest.raises(ValueError, match="Unknown tool"):
            toolset.execute("unknown_tool", args)

    def test_toolset_chat_tools(self):
        """Test conversion to ChatCompletionTool format."""
        toolset = CalculatorToolset()
        chat_tools = toolset.chat_tools

        assert len(chat_tools) == 1
        assert chat_tools[0].function.name == "calculate"

    def test_toolset_tool_names(self):
        """Test tool_names property."""
        toolset = CalculatorToolset()
        assert toolset.tool_names == ["calculate"]

    def test_toolset_get_toolspec(self):
        """Test getting toolspec by name."""
        toolset = CalculatorToolset()
        spec = toolset.get_toolspec("calculate")

        assert spec is not None
        assert spec.name == "calculate"

        assert toolset.get_toolspec("nonexistent") is None

    def test_toolset_serialization(self):
        """Test that toolset can be serialized and has kind field."""
        toolset = CalculatorToolset()
        data = toolset.model_dump()

        assert "kind" in data
        assert data["kind"].endswith("CalculatorToolset")


class TestCompositeToolset:
    """Tests for CompositeToolset."""

    def test_composite_toolset_combines_specs(self):
        """Test that CompositeToolset combines tool specs from all toolsets."""
        composite = CompositeToolset(
            toolsets=[
                CalculatorToolset(),
                SearchToolset(),
            ]
        )

        specs = composite.get_toolspecs()
        assert len(specs) == 2

        names = [s.name for s in specs]
        assert "calculate" in names
        assert "search" in names

    def test_composite_toolset_executes_correct_tool(self):
        """Test that CompositeToolset routes execution to correct toolset."""
        composite = CompositeToolset(
            toolsets=[
                CalculatorToolset(),
                SearchToolset(),
            ]
        )

        calc_result = composite.execute("calculate", CalculateParams(expression="5 * 5"))
        assert calc_result == "25"

        search_result = composite.execute("search", SearchParams(query="test"))
        assert search_result == "Search results for: test"

    def test_composite_toolset_unknown_tool(self):
        """Test that CompositeToolset raises error for unknown tool."""
        composite = CompositeToolset(toolsets=[CalculatorToolset()])

        with pytest.raises(ValueError, match="Unknown tool"):
            composite.execute("nonexistent", CalculateParams(expression="1"))

    def test_builtin_math_exposes_one_coherent_skill_group(self):
        composite = CompositeToolset(toolsets=[MathToolset()])

        assert composite.get_skill_specs() == [
            ReActSkillSpec(
                name="math_and_units",
                description="Arithmetic, statistics, rounding, and physical-unit conversion.",
                tool_names=["calculate", "convert_units"],
                instructions=(
                    "Use expression syntax only. Do not put prose, units, or currency symbols in expressions. "
                    "Use this for physical conversions; qualify US and Imperial volume standards."
                ),
                examples=[
                    "15 / 100 * 240",
                    "round(86.4 * 1.18 / 4, 2)",
                    "5 mi to km",
                    "90 km/h to m/s",
                ],
                order=10,
            ),
        ]

    def test_composite_merges_compatible_shared_skill_groups(self):
        composite = CompositeToolset(toolsets=[DuckDuckGoInstantAnswerToolset(), MediaWikiSearchToolset()])

        skills = composite.get_skill_specs()

        assert len(skills) == 1
        assert skills[0].name == "knowledge_lookup"
        assert skills[0].tool_names == ["mediawiki_search", "duckduckgo_instant_answer"]
        assert skills[0].instructions == (
            "Use a concise article title or topic, not a long question. This is not current web search. "
            "Use only when Instant Answers is requested or appropriate; it is not general web search."
        )
        assert len(skills[0].examples) == 4

    def test_builtin_skill_order_is_independent_of_composite_order(self):
        composite = CompositeToolset(
            toolsets=[
                DuckDuckGoInstantAnswerToolset(),
                TemporalToolset(),
                MediaWikiSearchToolset(),
                MathToolset(),
            ]
        )

        assert [skill.name for skill in composite.get_skill_specs()] == [
            "math_and_units",
            "dates_and_time",
            "knowledge_lookup",
        ]

    def test_composite_rejects_conflicting_shared_skill_groups(self):
        composite = CompositeToolset(toolsets=[MathToolset(), ConflictingSharedSkillToolset()])

        with pytest.raises(ValueError, match="conflicting descriptions"):
            composite.get_skill_specs()

    def test_skill_metadata_cannot_reference_unknown_tools(self):
        with pytest.raises(ValueError, match="unknown tools"):
            ReActAgent._validate_skill_specs(BrokenSkillToolset(), BrokenSkillToolset().get_skill_specs())

    def test_skill_metadata_must_cover_every_tool(self):
        with pytest.raises(ValueError, match="does not cover tools"):
            ReActAgent._validate_skill_specs(PartiallySkilledToolset(), PartiallySkilledToolset().get_skill_specs())

    def test_composite_skill_cannot_claim_a_sibling_tool(self):
        composite = CompositeToolset(toolsets=[CalculatorToolset(), SiblingClaimingToolset()])

        with pytest.raises(ValueError, match="not owned by its toolset"):
            composite.get_skill_specs()


class TestReActAgentConfig:
    """Tests for ReActAgentConfig."""

    def test_config_basic(self):
        """Test basic config creation."""
        config = ReActAgentConfig(
            model="gpt-4",
            toolset=CalculatorToolset(),
        )

        assert config.model == "gpt-4"
        assert config.max_iterations == 10  # default
        assert config.toolset is not None
        assert config.failure_handling == "safe"
        assert config.tool_disclosure == "all"

    def test_legacy_failure_handling_is_supported(self):
        config = ReActAgentConfig(model="gpt-4", toolset=CalculatorToolset(), failure_handling="legacy")

        assert config.failure_handling == "legacy"

    def test_config_with_all_options(self):
        """Test config with all options set."""
        config = ReActAgentConfig(
            model="gpt-4",
            system_prompt="Custom prompt",
            temperature=0.7,
            max_tokens=1000,
            max_iterations=5,
            toolset=CalculatorToolset(),
        )

        assert config.system_prompt == "Custom prompt"
        assert config.temperature == 0.7
        assert config.max_tokens == 1000
        assert config.max_iterations == 5

    def test_config_serialization(self):
        """Test that config can be serialized to dict."""
        config = ReActAgentConfig(
            model="gpt-4",
            max_iterations=5,
            toolset=CalculatorToolset(),
        )

        data = config.model_dump()
        assert data["model"] == "gpt-4"
        assert data["max_iterations"] == 5
        assert "toolset" in data
        assert "kind" in data["toolset"]

    def test_config_from_dict_with_toolset(self):
        """Test loading config from dict with toolset FQCN."""
        config_dict = {
            "model": "gpt-4",
            "max_iterations": 5,
            "toolset": {
                "kind": f"{CalculatorToolset.__module__}.{CalculatorToolset.__qualname__}",
            },
        }

        config = ReActAgentConfig.model_validate(config_dict)
        assert config.model == "gpt-4"
        assert isinstance(config.toolset, CalculatorToolset)


class TestReActAgent:
    """Tests for ReActAgent."""

    def test_agent_simple_response(self, generator, build_message_from_payload):
        """Test agent with a simple response (no tool calls)."""
        # Create agent spec
        agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("react_agent")
            .set_name("ReAct Agent")
            .set_description("A ReAct agent for testing")
            .set_properties(
                ReActAgentConfig(
                    model="test-model",
                    toolset=CalculatorToolset(),
                )
            )
            .build_spec()
        )

        mock_dependency_map = {
            "llm": DependencySpec(
                class_name="rustic_ai.litellm.agent_ext.llm.LiteLLMResolver",
                properties={"model": "test-model"},
            ),
        }

        agent, results = wrap_agent_for_testing(
            agent_spec,
            dependency_map=mock_dependency_map,
        )

        # Patch the LLM call
        with patch.object(
            agent,
            "_call_llm_direct",
            return_value=create_mock_response("The answer is 42."),
        ):
            agent._on_message(
                build_message_from_payload(
                    generator,
                    ChatCompletionRequest(messages=[UserMessage(content="What is the answer?")]),
                )
            )

        assert len(results) == 1
        response = ChatCompletionResponse.model_validate(results[0].payload)
        assert response.choices[0].message.content == "The answer is 42."
        assert response.choices[0].finish_reason == FinishReason.stop
        # Check react_trace in provider_specific_fields
        provider_fields = response.choices[0].provider_specific_fields
        assert provider_fields is not None
        assert "react_trace" in provider_fields
        assert len(provider_fields["react_trace"]) == 0  # No tool calls

    def test_provider_error_is_emitted_as_typed_error(self, generator, build_message_from_payload):
        agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("react_agent")
            .set_name("ReAct Agent")
            .set_description("A ReAct agent for testing")
            .set_properties(
                ReActAgentConfig(
                    model="test-model",
                    toolset=CalculatorToolset(),
                )
            )
            .build_spec()
        )
        agent, results = wrap_agent_for_testing(
            agent_spec,
            dependency_map={
                "llm": DependencySpec(
                    class_name="rustic_ai.litellm.agent_ext.llm.LiteLLMResolver",
                    properties={"model": "test-model"},
                )
            },
        )
        provider_error = openai.RateLimitError(
            "You have no credits remaining. PRIVATE_PROVIDER_DETAIL",
            response=httpx.Response(
                429,
                request=httpx.Request("POST", "https://provider.invalid/chat"),
                json={"error": {"code": "insufficient_quota"}},
            ),
            body={"error": {"code": "insufficient_quota"}},
        )

        with patch.object(agent, "_call_llm_direct", side_effect=provider_error):
            agent._on_message(
                build_message_from_payload(
                    generator,
                    ChatCompletionRequest(messages=[UserMessage(content="PRIVATE_USER_PROMPT")]),
                )
            )

        assert len(results) == 1
        assert results[0].format.endswith(".ChatCompletionError")
        error = ChatCompletionError.model_validate(results[0].payload)
        assert error.status_code == ResponseCodes.RATE_LIMIT_ERROR
        assert error.body == {"error": {"code": "insufficient_quota"}}
        assert error.request_messages[0].content == "PRIVATE_USER_PROMPT"

    @pytest.mark.parametrize(
        ("provider_error", "expected_status"),
        [
            (
                openai.APIConnectionError(
                    message="PRIVATE_CONNECTION_DETAIL",
                    request=httpx.Request("POST", "https://provider.invalid/chat"),
                ),
                ResponseCodes.API_CONNECTION_ERROR,
            ),
            (
                openai.APITimeoutError(
                    request=httpx.Request("POST", "https://provider.invalid/chat")
                ),
                ResponseCodes.API_TIMEOUT_ERROR,
            ),
        ],
    )
    def test_provider_transport_error_is_emitted_as_typed_error(
        self,
        generator,
        build_message_from_payload,
        provider_error,
        expected_status,
    ):
        agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("react_agent")
            .set_name("ReAct Agent")
            .set_description("A ReAct agent for testing")
            .set_properties(
                ReActAgentConfig(
                    model="test-model",
                    toolset=CalculatorToolset(),
                )
            )
            .build_spec()
        )
        agent, results = wrap_agent_for_testing(
            agent_spec,
            dependency_map={
                "llm": DependencySpec(
                    class_name="rustic_ai.litellm.agent_ext.llm.LiteLLMResolver",
                    properties={"model": "test-model"},
                )
            },
        )

        with patch.object(agent, "_call_llm_direct", side_effect=provider_error):
            agent._on_message(
                build_message_from_payload(
                    generator,
                    ChatCompletionRequest(messages=[UserMessage(content="PRIVATE_USER_PROMPT")]),
                )
            )

        assert len(results) == 1
        assert results[0].format.endswith(".ChatCompletionError")
        error = ChatCompletionError.model_validate(results[0].payload)
        assert error.status_code == expected_status
        assert error.request_messages[0].content == "PRIVATE_USER_PROMPT"

    def test_unexpected_error_is_emitted_once_as_internal_error(self, generator, build_message_from_payload):
        agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("react_agent")
            .set_name("ReAct Agent")
            .set_description("A ReAct agent for testing")
            .set_properties(
                ReActAgentConfig(
                    model="test-model",
                    toolset=CalculatorToolset(),
                )
            )
            .build_spec()
        )
        agent, results = wrap_agent_for_testing(
            agent_spec,
            dependency_map={
                "llm": DependencySpec(
                    class_name="rustic_ai.litellm.agent_ext.llm.LiteLLMResolver",
                    properties={"model": "test-model"},
                )
            },
        )

        with patch.object(agent, "_call_llm_direct", side_effect=RuntimeError("PRIVATE_INTERNAL_DETAIL")):
            agent._on_message(
                build_message_from_payload(
                    generator,
                    ChatCompletionRequest(messages=[UserMessage(content="PRIVATE_USER_PROMPT")]),
                )
            )

        assert len(results) == 1
        assert results[0].format.endswith(".ChatCompletionError")
        error = ChatCompletionError.model_validate(results[0].payload)
        assert error.status_code == ResponseCodes.INTERNAL_SERVER_ERROR
        assert error.message == "Error in ReAct loop: PRIVATE_INTERNAL_DETAIL"

    def test_agent_with_tool_call(self, generator, build_message_from_payload):
        """Test agent with tool calls."""
        agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("react_agent")
            .set_name("ReAct Agent")
            .set_description("A ReAct agent for testing")
            .set_properties(
                ReActAgentConfig(
                    model="test-model",
                    toolset=CalculatorToolset(),
                )
            )
            .build_spec()
        )

        mock_dependency_map = {
            "llm": DependencySpec(
                class_name="rustic_ai.litellm.agent_ext.llm.LiteLLMResolver",
                properties={"model": "test-model"},
            ),
        }

        agent, results = wrap_agent_for_testing(
            agent_spec,
            dependency_map=mock_dependency_map,
        )

        # Simulate: first call returns tool call, second call returns answer
        responses = [
            create_mock_response(
                content="I need to calculate this.",
                tool_calls=[create_tool_call("call_1", "calculate", {"expression": "2 + 2"})],
                finish_reason=FinishReason.tool_calls,
            ),
            create_mock_response("The result is 4."),
        ]

        call_count = [0]

        def mock_call_llm(llm, request):
            response = responses[call_count[0]]
            call_count[0] += 1
            return response

        with patch.object(agent, "_call_llm_direct", side_effect=mock_call_llm):
            agent._on_message(
                build_message_from_payload(
                    generator,
                    ChatCompletionRequest(messages=[UserMessage(content="What is 2 + 2?")]),
                )
            )

        assert len(results) == 1
        response = ChatCompletionResponse.model_validate(results[0].payload)
        assert response.choices[0].message.content == "The result is 4."
        assert response.choices[0].finish_reason == FinishReason.stop
        # Check react_trace in provider_specific_fields
        provider_fields = response.choices[0].provider_specific_fields
        assert provider_fields is not None
        assert "react_trace" in provider_fields
        trace = provider_fields["react_trace"]
        assert len(trace) == 1
        assert trace[0]["action"] == "calculate"
        assert trace[0]["observation"] == "4"

    def test_agent_with_system_message_appended(self, generator, build_message_from_payload):
        """Test that incoming SystemMessage is preserved and appended before ReAct prompt."""
        agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("react_agent")
            .set_name("ReAct Agent")
            .set_description("A ReAct agent for testing")
            .set_properties(
                ReActAgentConfig(
                    model="test-model",
                    toolset=CalculatorToolset(),
                )
            )
            .build_spec()
        )

        mock_dependency_map = {
            "llm": DependencySpec(
                class_name="rustic_ai.litellm.agent_ext.llm.LiteLLMResolver",
                properties={"model": "test-model"},
            ),
        }

        agent, results = wrap_agent_for_testing(
            agent_spec,
            dependency_map=mock_dependency_map,
        )

        captured_requests = []

        def capture_llm_call(llm, request):
            captured_requests.append(request)
            return create_mock_response("Done.")

        custom_system_content = "You are a math tutor. Be helpful and encouraging."

        with patch.object(agent, "_call_llm_direct", side_effect=capture_llm_call):
            agent._on_message(
                build_message_from_payload(
                    generator,
                    ChatCompletionRequest(
                        messages=[
                            SystemMessage(content=custom_system_content),
                            UserMessage(content="What is 5 + 5?"),
                        ]
                    ),
                )
            )

        # Verify the LLM was called
        assert len(captured_requests) == 1
        llm_request = captured_requests[0]

        # The messages should have: user's SystemMessage, ReAct SystemMessage, UserMessage
        assert len(llm_request.messages) >= 3

        # First message should be the user's custom system message
        assert isinstance(llm_request.messages[0], SystemMessage)
        assert llm_request.messages[0].content == custom_system_content

        # Second message should be the ReAct system prompt
        assert isinstance(llm_request.messages[1], SystemMessage)
        assert llm_request.messages[1].content == DEFAULT_REACT_SYSTEM_PROMPT

        # Last message should be the user query
        assert isinstance(llm_request.messages[-1], UserMessage)
        assert llm_request.messages[-1].content == "What is 5 + 5?"

        # Verify response
        assert len(results) == 1
        response = ChatCompletionResponse.model_validate(results[0].payload)
        assert response.choices[0].message.content == "Done."


class TestReActModels:
    """Tests for ReAct model classes."""

    def test_react_step(self):
        """Test ReActStep model."""
        step = ReActStep(
            thought="I should calculate this",
            action="calculate",
            action_input={"expression": "1 + 1"},
            observation="2",
        )

        assert step.thought == "I should calculate this"
        assert step.action == "calculate"
        assert step.action_input == {"expression": "1 + 1"}
        assert step.observation == "2"

    def test_react_step_serialization(self):
        """Test ReActStep serialization for storage in provider_specific_fields."""
        step = ReActStep(
            thought="Let me think...",
            action="search",
            action_input={"query": "test"},
            observation="Found results",
        )

        data = step.model_dump()
        assert data["thought"] == "Let me think..."
        assert data["action"] == "search"
        assert data["action_input"] == {"query": "test"}
        assert data["observation"] == "Found results"


class TestSafeFailureHandling:
    @staticmethod
    def build_agent(
        toolset: ReActToolset,
        *,
        failure_handling="safe",
        max_iterations=5,
        tool_disclosure="all",
        system_prompt=None,
        skill_activation_followup="auto",
        skill_activation_observation="standard",
        skill_disclosure_progression="sticky",
    ):
        agent_spec = (
            AgentBuilder(ReActAgent)
            .set_id("safe_react_agent")
            .set_name("Safe ReAct Agent")
            .set_description("Exercise deterministic ReAct failure handling")
            .set_properties(
                ReActAgentConfig(
                    model="test-model",
                    toolset=toolset,
                    failure_handling=failure_handling,
                    tool_disclosure=tool_disclosure,
                    skill_activation_followup=skill_activation_followup,
                    skill_activation_observation=skill_activation_observation,
                    skill_disclosure_progression=skill_disclosure_progression,
                    max_iterations=max_iterations,
                    system_prompt=system_prompt,
                )
            )
            .build_spec()
        )
        dependencies = {
            "llm": DependencySpec(
                class_name="rustic_ai.litellm.agent_ext.llm.LiteLLMResolver",
                properties={"model": "test-model"},
            )
        }
        return wrap_agent_for_testing(agent_spec, dependency_map=dependencies)

    @staticmethod
    def run(agent, responses, generator, build_message_from_payload):
        with patch.object(agent, "_call_llm_direct", side_effect=responses):
            agent._on_message(
                build_message_from_payload(
                    generator,
                    ChatCompletionRequest(messages=[UserMessage(content="Use the requested tools.")]),
                )
            )

    def test_suppresses_duplicate_execution_and_preserves_verified_result(self, generator, build_message_from_payload):
        CountingMathToolset.execution_count = 0
        agent, results = self.build_agent(CountingMathToolset())
        tool_call = create_tool_call("call_1", "calculate", {"expression": "2+2"})
        duplicate = create_tool_call("call_2", "calculate", {"expression": "2+2"})

        self.run(
            agent,
            [
                create_mock_response("Calculate.", [tool_call], FinishReason.tool_calls),
                create_mock_response("Again.", [duplicate], FinishReason.tool_calls),
            ],
            generator,
            build_message_from_payload,
        )

        response = ChatCompletionResponse.model_validate(results[-1].payload)
        fields = response.choices[0].provider_specific_fields
        trace = fields["react_trace"]
        assert CountingMathToolset.execution_count == 1
        assert [step["executed"] for step in trace] == [True, False]
        assert fields["termination_reason"] == "duplicate_tool_call"
        assert fields["success"] is True
        assert "2+2 = 4" in response.choices[0].message.content

    def test_progressively_discloses_selected_skill_tools(self, generator, build_message_from_payload):
        agent, results = self.build_agent(MathToolset(), tool_disclosure="skills")
        self.run(
            agent,
            [
                create_mock_response(
                    "Select math and units.",
                    [
                        create_tool_call(
                            "skill_1",
                            "activate_tool_skill",
                            {"skill": "math_and_units"},
                        )
                    ],
                    FinishReason.tool_calls,
                ),
                create_mock_response(
                    "Calculate.",
                    [create_tool_call("call_1", "calculate", {"expression": "2+2"})],
                    FinishReason.tool_calls,
                ),
                create_mock_response("The result is 4."),
            ],
            generator,
            build_message_from_payload,
        )

        response = ChatCompletionResponse.model_validate(results[-1].payload)
        trace = response.choices[0].provider_specific_fields["react_trace"]

        assert [step["action"] for step in trace] == [
            "activate_tool_skill",
            "calculate",
        ]
        assert trace[0]["executed"] is False
        assert json.loads(trace[0]["observation"])["available_tools"] == [
            "calculate",
            "convert_units",
        ]
        assert response.choices[0].message.content == "The result is 4."

    def test_required_skill_followup_excludes_selector_and_requires_domain_tool(
        self, generator, build_message_from_payload
    ):
        captured_requests = []

        def capture(_llm, request):
            captured_requests.append(request)
            if len(captured_requests) == 1:
                return create_mock_response(
                    "Activate math and units.",
                    [
                        create_tool_call(
                            "skill_1",
                            "activate_tool_skill",
                            {"skill": "math_and_units"},
                        )
                    ],
                    FinishReason.tool_calls,
                )
            if len(captured_requests) == 2:
                return create_mock_response(
                    "Calculate.",
                    [create_tool_call("call_1", "calculate", {"expression": "2+2"})],
                    FinishReason.tool_calls,
                )
            return create_mock_response("The result is 4.")

        agent, _ = self.build_agent(
            MathToolset(),
            tool_disclosure="skills",
            skill_activation_followup="required",
        )
        self.run(agent, capture, generator, build_message_from_payload)

        assert [tool.function.name for tool in captured_requests[0].tools] == ["activate_tool_skill"]
        assert [tool.function.name for tool in captured_requests[1].tools] == [
            "calculate",
            "convert_units",
        ]
        assert captured_requests[1].tool_choice == "required"
        assert {tool.function.name for tool in captured_requests[2].tools} == {
            "activate_tool_skill",
            "calculate",
            "convert_units",
        }
        assert captured_requests[2].tool_choice is None

    def test_explicit_skill_observation_requires_a_domain_action(self, generator, build_message_from_payload):
        agent, results = self.build_agent(
            MathToolset(),
            tool_disclosure="skills",
            skill_activation_observation="explicit",
        )
        self.run(
            agent,
            [
                create_mock_response(
                    "Activate math and units.",
                    [
                        create_tool_call(
                            "skill_1",
                            "activate_tool_skill",
                            {"skill": "math_and_units"},
                        )
                    ],
                    FinishReason.tool_calls,
                ),
                create_mock_response("Ready."),
            ],
            generator,
            build_message_from_payload,
        )

        response = ChatCompletionResponse.model_validate(results[-1].payload)
        observation = json.loads(response.choices[0].provider_specific_fields["react_trace"][0]["observation"])
        assert "did not answer the user" in observation["next_action"]

    def test_can_expand_all_tools_after_first_success(self, generator, build_message_from_payload):
        captured_requests = []

        def capture(_llm, request):
            captured_requests.append(request)
            if len(captured_requests) == 1:
                return create_mock_response(
                    "Activate math and units.",
                    [
                        create_tool_call(
                            "skill_1",
                            "activate_tool_skill",
                            {"skill": "math_and_units"},
                        )
                    ],
                    FinishReason.tool_calls,
                )
            if len(captured_requests) == 2:
                return create_mock_response(
                    "Calculate.",
                    [create_tool_call("call_1", "calculate", {"expression": "2+2"})],
                    FinishReason.tool_calls,
                )
            return create_mock_response("The result is 4.")

        agent, _ = self.build_agent(
            MathToolset(),
            tool_disclosure="skills",
            skill_disclosure_progression="expand_after_first_success",
        )
        self.run(agent, capture, generator, build_message_from_payload)

        assert [tool.function.name for tool in captured_requests[0].tools] == ["activate_tool_skill"]
        assert {tool.function.name for tool in captured_requests[1].tools} == {
            "activate_tool_skill",
            "calculate",
            "convert_units",
        }
        assert {tool.function.name for tool in captured_requests[2].tools} == {
            "calculate",
            "convert_units",
        }

    def test_skill_mode_falls_back_to_all_tools_without_skill_metadata(self, generator, build_message_from_payload):
        agent, results = self.build_agent(CalculatorToolset(), tool_disclosure="skills")
        self.run(
            agent,
            [
                create_mock_response(
                    "Calculate.",
                    [create_tool_call("call_1", "calculate", {"expression": "2+2"})],
                    FinishReason.tool_calls,
                ),
                create_mock_response("The result is 4."),
            ],
            generator,
            build_message_from_payload,
        )

        response = ChatCompletionResponse.model_validate(results[-1].payload)
        trace = response.choices[0].provider_specific_fields["react_trace"]
        assert [step["action"] for step in trace] == ["calculate"]

    def test_skill_selector_uses_a_singular_dynamic_enum(self):
        toolset = CompositeToolset(toolsets=[MathToolset(), TemporalToolset()])
        spec = ReActAgent._skill_selector_spec(toolset.get_skill_specs())
        schema = spec.chat_tool.function.parameters.model_dump(mode="json")

        assert spec.name == "activate_tool_skill"
        assert schema["required"] == ["skill"]
        assert schema["properties"]["skill"]["enum"] == [
            "math_and_units",
            "dates_and_time",
        ]
        assert "skills" not in schema["properties"]
        assert "do not predict or activate every skill upfront" in spec.description

    def test_incrementally_activates_a_second_skill_after_using_the_first(self, generator, build_message_from_payload):
        toolset = CompositeToolset(toolsets=[MathToolset(), TemporalToolset()])
        agent, results = self.build_agent(toolset, tool_disclosure="skills")
        self.run(
            agent,
            [
                create_mock_response(
                    "Activate math and units.",
                    [
                        create_tool_call(
                            "skill_1",
                            "activate_tool_skill",
                            {"skill": "math_and_units"},
                        )
                    ],
                    FinishReason.tool_calls,
                ),
                create_mock_response(
                    "Calculate.",
                    [create_tool_call("call_1", "calculate", {"expression": "2+2"})],
                    FinishReason.tool_calls,
                ),
                create_mock_response(
                    "Now activate dates and time.",
                    [
                        create_tool_call(
                            "skill_2",
                            "activate_tool_skill",
                            {"skill": "dates_and_time"},
                        )
                    ],
                    FinishReason.tool_calls,
                ),
                create_mock_response(
                    "Inspect the date.",
                    [
                        create_tool_call(
                            "call_2",
                            "get_date_info",
                            {"date": "2026-08-08"},
                        )
                    ],
                    FinishReason.tool_calls,
                ),
                create_mock_response("The results are 4 and Saturday."),
            ],
            generator,
            build_message_from_payload,
        )

        response = ChatCompletionResponse.model_validate(results[-1].payload)
        trace = response.choices[0].provider_specific_fields["react_trace"]
        assert [step["action"] for step in trace] == [
            "activate_tool_skill",
            "calculate",
            "activate_tool_skill",
            "get_date_info",
        ]
        second_activation = json.loads(trace[2]["observation"])
        assert second_activation["active_skills"] == [
            "dates_and_time",
            "math_and_units",
        ]
        assert second_activation["available_tools"] == [
            "calculate",
            "convert_units",
            "get_current_time",
            "convert_datetime",
            "get_date_info",
            "add_calendar_period",
            "add_business_days",
            "calendar_days_between",
            "business_days_between",
        ]

    def test_allows_multiple_singular_activations_in_one_model_response(self, generator, build_message_from_payload):
        toolset = CompositeToolset(toolsets=[MathToolset(), TemporalToolset()])
        agent, results = self.build_agent(toolset, tool_disclosure="skills")
        self.run(
            agent,
            [
                create_mock_response(
                    "Activate both independently.",
                    [
                        create_tool_call(
                            "skill_1",
                            "activate_tool_skill",
                            {"skill": "math_and_units"},
                        ),
                        create_tool_call(
                            "skill_2",
                            "activate_tool_skill",
                            {"skill": "dates_and_time"},
                        ),
                    ],
                    FinishReason.tool_calls,
                ),
                create_mock_response("The tools are ready."),
            ],
            generator,
            build_message_from_payload,
        )

        response = ChatCompletionResponse.model_validate(results[-1].payload)
        trace = response.choices[0].provider_specific_fields["react_trace"]
        assert [step["outcome"] for step in trace] == ["success", "success"]
        assert json.loads(trace[-1]["observation"])["active_skills"] == [
            "dates_and_time",
            "math_and_units",
        ]

    def test_domain_tool_must_be_disclosed_in_a_later_model_round(self, generator, build_message_from_payload):
        agent, results = self.build_agent(MathToolset(), tool_disclosure="skills")
        self.run(
            agent,
            [
                create_mock_response(
                    "Activate and call too early.",
                    [
                        create_tool_call(
                            "skill_1",
                            "activate_tool_skill",
                            {"skill": "math_and_units"},
                        ),
                        create_tool_call("call_early", "calculate", {"expression": "2+2"}),
                    ],
                    FinishReason.tool_calls,
                ),
                create_mock_response(
                    "Call after disclosure.",
                    [create_tool_call("call_1", "calculate", {"expression": "2+2"})],
                    FinishReason.tool_calls,
                ),
                create_mock_response("The result is 4."),
            ],
            generator,
            build_message_from_payload,
        )

        response = ChatCompletionResponse.model_validate(results[-1].payload)
        fields = response.choices[0].provider_specific_fields
        trace = fields["react_trace"]
        assert trace[1]["error_code"] == "tool_not_disclosed"
        assert trace[1]["executed"] is False
        assert trace[1]["model_round"] == 1
        assert trace[2]["outcome"] == "success"
        assert trace[2]["model_round"] == 2
        assert fields["success"] is True
        assert fields["unresolved_tool_failures"] == []

    def test_custom_prompt_gets_incremental_contract_from_selector(self, generator, build_message_from_payload):
        captured_requests = []

        def capture(_llm, request):
            captured_requests.append(request)
            return create_mock_response("No tool is needed.")

        agent, _ = self.build_agent(
            MathToolset(),
            tool_disclosure="skills",
            system_prompt="Custom replacement prompt.",
        )
        self.run(agent, capture, generator, build_message_from_payload)

        request = captured_requests[0]
        system_messages = [message for message in request.messages if isinstance(message, SystemMessage)]
        assert system_messages[-1].content == "Custom replacement prompt."
        assert "Call this selector again later" in request.tools[0].function.description

    def test_skill_activation_uses_global_iteration_budget_not_a_selector_cap(
        self, generator, build_message_from_payload
    ):
        toolset = CompositeToolset(toolsets=[MathToolset(), TemporalToolset(), MediaWikiSearchToolset()])
        agent, results = self.build_agent(toolset, tool_disclosure="skills", max_iterations=4)
        self.run(
            agent,
            [
                create_mock_response(
                    "Math and units.",
                    [
                        create_tool_call(
                            "skill_1",
                            "activate_tool_skill",
                            {"skill": "math_and_units"},
                        )
                    ],
                    FinishReason.tool_calls,
                ),
                create_mock_response(
                    "Dates and time.",
                    [
                        create_tool_call(
                            "skill_2",
                            "activate_tool_skill",
                            {"skill": "dates_and_time"},
                        )
                    ],
                    FinishReason.tool_calls,
                ),
                create_mock_response(
                    "Knowledge lookup.",
                    [
                        create_tool_call(
                            "skill_3",
                            "activate_tool_skill",
                            {"skill": "knowledge_lookup"},
                        )
                    ],
                    FinishReason.tool_calls,
                ),
                create_mock_response("All three are active."),
            ],
            generator,
            build_message_from_payload,
        )

        response = ChatCompletionResponse.model_validate(results[-1].payload)
        fields = response.choices[0].provider_specific_fields
        assert fields["success"] is True
        assert fields["termination_reason"] == "completed"
        assert len(fields["react_trace"]) == 3

    def test_retries_invalid_skill_activation_and_stops_on_same_error_class(
        self, generator, build_message_from_payload
    ):
        toolset = CompositeToolset(toolsets=[MathToolset(), TemporalToolset()])
        agent, results = self.build_agent(toolset, tool_disclosure="skills")
        self.run(
            agent,
            [
                create_mock_response(
                    "Unknown.",
                    [create_tool_call("skill_1", "activate_tool_skill", {"skill": "mathematics"})],
                    FinishReason.tool_calls,
                ),
                create_mock_response(
                    "Still unknown.",
                    [create_tool_call("skill_2", "activate_tool_skill", {"skill": "math"})],
                    FinishReason.tool_calls,
                ),
            ],
            generator,
            build_message_from_payload,
        )

        response = ChatCompletionResponse.model_validate(results[-1].payload)
        fields = response.choices[0].provider_specific_fields
        assert fields["termination_reason"] == "tool_retry_exhausted"
        assert [step["error_code"] for step in fields["react_trace"]] == [
            "unknown_skill",
            "unknown_skill",
        ]
        assert [step["attempt"] for step in fields["react_trace"]] == [1, 2]

    def test_already_active_skill_can_be_corrected_to_another_skill(self, generator, build_message_from_payload):
        toolset = CompositeToolset(toolsets=[MathToolset(), TemporalToolset()])
        agent, results = self.build_agent(toolset, tool_disclosure="skills")
        self.run(
            agent,
            [
                create_mock_response(
                    "Math and units.",
                    [
                        create_tool_call(
                            "skill_1",
                            "activate_tool_skill",
                            {"skill": "math_and_units"},
                        )
                    ],
                    FinishReason.tool_calls,
                ),
                create_mock_response(
                    "Repeat math and units.",
                    [
                        create_tool_call(
                            "skill_2",
                            "activate_tool_skill",
                            {"skill": "math_and_units"},
                        )
                    ],
                    FinishReason.tool_calls,
                ),
                create_mock_response(
                    "Correct to dates and time.",
                    [
                        create_tool_call(
                            "skill_3",
                            "activate_tool_skill",
                            {"skill": "dates_and_time"},
                        )
                    ],
                    FinishReason.tool_calls,
                ),
                create_mock_response("Both are active."),
            ],
            generator,
            build_message_from_payload,
        )

        response = ChatCompletionResponse.model_validate(results[-1].payload)
        fields = response.choices[0].provider_specific_fields
        assert fields["react_trace"][1]["error_code"] == "already_active"
        assert fields["react_trace"][1]["outcome"] == "retryable_error"
        assert fields["success"] is True
        assert fields["unresolved_tool_failures"] == []

    def test_allows_one_corrected_argument_attempt(self, generator, build_message_from_payload):
        agent, results = self.build_agent(MathToolset())
        self.run(
            agent,
            [
                create_mock_response(
                    "Wrong shape.",
                    [create_tool_call("call_1", "calculate", {"value": 4})],
                    FinishReason.tool_calls,
                ),
                create_mock_response(
                    "Correct it.",
                    [create_tool_call("call_2", "calculate", {"expression": "2+2"})],
                    FinishReason.tool_calls,
                ),
                create_mock_response("The verified answer is 4."),
            ],
            generator,
            build_message_from_payload,
        )

        response = ChatCompletionResponse.model_validate(results[-1].payload)
        fields = response.choices[0].provider_specific_fields
        assert response.choices[0].message.content == "The verified answer is 4."
        assert fields["termination_reason"] == "completed"
        assert fields["unresolved_tool_failures"] == []

    def test_stops_after_second_error_of_same_class(self, generator, build_message_from_payload):
        agent, results = self.build_agent(MathToolset())
        self.run(
            agent,
            [
                create_mock_response(
                    "Try prose.",
                    [create_tool_call("call_1", "calculate", {"expression": "15% of 240"})],
                    FinishReason.tool_calls,
                ),
                create_mock_response(
                    "Try other prose.",
                    [create_tool_call("call_2", "calculate", {"expression": "15 percent of 240"})],
                    FinishReason.tool_calls,
                ),
            ],
            generator,
            build_message_from_payload,
        )

        response = ChatCompletionResponse.model_validate(results[-1].payload)
        fields = response.choices[0].provider_specific_fields
        assert fields["termination_reason"] == "tool_retry_exhausted"
        assert fields["success"] is False
        assert len(fields["react_trace"]) == 2

    def test_ambiguous_unit_returns_deterministic_clarification(self, generator, build_message_from_payload):
        agent, results = self.build_agent(MathToolset())
        self.run(
            agent,
            [
                create_mock_response(
                    "Convert it.",
                    [
                        create_tool_call(
                            "call_1",
                            "convert_units",
                            {"value": 3, "from_unit": "gallon", "to_unit": "l"},
                        )
                    ],
                    FinishReason.tool_calls,
                )
            ],
            generator,
            build_message_from_payload,
        )

        response = ChatCompletionResponse.model_validate(results[-1].payload)
        fields = response.choices[0].provider_specific_fields
        assert fields["termination_reason"] == "clarification_required"
        assert "specify US or Imperial" in response.choices[0].message.content

    def test_failed_lookup_replaces_unsupported_memory_answer(self, generator, build_message_from_payload):
        FixedLookupToolset.outcomes = ["no_result"]
        FixedLookupToolset.execution_count = 0
        agent, results = self.build_agent(FixedLookupToolset())
        self.run(
            agent,
            [
                create_mock_response(
                    "Look it up.",
                    [
                        create_tool_call(
                            "call_1",
                            "duckduckgo_instant_answer",
                            {"query": "capital of France"},
                        )
                    ],
                    FinishReason.tool_calls,
                ),
                create_mock_response("The capital is Paris."),
            ],
            generator,
            build_message_from_payload,
        )

        response = ChatCompletionResponse.model_validate(results[-1].payload)
        fields = response.choices[0].provider_specific_fields
        assert fields["termination_reason"] == "unresolved_tool_failure"
        assert "Paris" not in response.choices[0].message.content
        assert "could not verify" in response.choices[0].message.content

    def test_corrected_lookup_resolves_previous_no_result(self, generator, build_message_from_payload):
        FixedLookupToolset.outcomes = ["no_result", "ok"]
        FixedLookupToolset.execution_count = 0
        agent, results = self.build_agent(FixedLookupToolset())
        self.run(
            agent,
            [
                create_mock_response(
                    "Question query.",
                    [
                        create_tool_call(
                            "call_1",
                            "duckduckgo_instant_answer",
                            {"query": "capital of France"},
                        )
                    ],
                    FinishReason.tool_calls,
                ),
                create_mock_response(
                    "Topic query.",
                    [create_tool_call("call_2", "duckduckgo_instant_answer", {"query": "France"})],
                    FinishReason.tool_calls,
                ),
                create_mock_response("The verified capital is Paris."),
            ],
            generator,
            build_message_from_payload,
        )

        response = ChatCompletionResponse.model_validate(results[-1].payload)
        fields = response.choices[0].provider_specific_fields
        assert fields["success"] is True
        assert fields["unresolved_tool_failures"] == []
        assert response.choices[0].message.content == "The verified capital is Paris."

    def test_mixed_request_returns_verified_partial_results(self, generator, build_message_from_payload):
        FixedLookupToolset.outcomes = ["no_result"]
        FixedLookupToolset.execution_count = 0
        toolset = CompositeToolset(toolsets=[MathToolset(), FixedLookupToolset()])
        agent, results = self.build_agent(toolset)
        self.run(
            agent,
            [
                create_mock_response(
                    "Complete both parts.",
                    [
                        create_tool_call("call_1", "calculate", {"expression": "6*7"}),
                        create_tool_call(
                            "call_2",
                            "duckduckgo_instant_answer",
                            {"query": "unknown topic"},
                        ),
                    ],
                    FinishReason.tool_calls,
                ),
                create_mock_response("42, and I think the fact is probably true."),
            ],
            generator,
            build_message_from_payload,
        )

        response = ChatCompletionResponse.model_validate(results[-1].payload)
        content = response.choices[0].message.content
        assert "6*7 = 42" in content
        assert "could not verify" in content
        assert response.choices[0].provider_specific_fields["success"] is False

    def test_legacy_mode_executes_duplicates_and_keeps_model_answer(self, generator, build_message_from_payload):
        CountingMathToolset.execution_count = 0
        agent, results = self.build_agent(CountingMathToolset(), failure_handling="legacy")
        self.run(
            agent,
            [
                create_mock_response(
                    "Calculate.",
                    [create_tool_call("call_1", "calculate", {"expression": "2+2"})],
                    FinishReason.tool_calls,
                ),
                create_mock_response(
                    "Repeat.",
                    [create_tool_call("call_2", "calculate", {"expression": "2+2"})],
                    FinishReason.tool_calls,
                ),
                create_mock_response("The answer is 4."),
            ],
            generator,
            build_message_from_payload,
        )

        response = ChatCompletionResponse.model_validate(results[-1].payload)
        assert CountingMathToolset.execution_count == 2
        assert response.choices[0].message.content == "The answer is 4."

    def test_max_iterations_preserves_verified_result(self, generator, build_message_from_payload):
        agent, results = self.build_agent(MathToolset(), max_iterations=1)
        self.run(
            agent,
            [
                create_mock_response(
                    "Calculate.",
                    [create_tool_call("call_1", "calculate", {"expression": "2+2"})],
                    FinishReason.tool_calls,
                )
            ],
            generator,
            build_message_from_payload,
        )

        response = ChatCompletionResponse.model_validate(results[-1].payload)
        assert "2+2 = 4" in response.choices[0].message.content
        assert response.choices[0].provider_specific_fields["termination_reason"] == "max_iterations"
