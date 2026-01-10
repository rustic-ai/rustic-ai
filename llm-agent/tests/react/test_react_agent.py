import json
from typing import Any, List, Optional
from unittest.mock import patch

from pydantic import BaseModel
import pytest

from rustic_ai.core.guild.agent_ext.depends.dependency_resolver import DependencySpec
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    AssistantMessage,
    ChatCompletionMessageToolCall,
    ChatCompletionResponse,
    Choice,
    CompletionUsage,
    FinishReason,
    FunctionCall,
    ToolType,
)
from rustic_ai.core.guild.agent_ext.depends.llm.tools_manager import ToolSpec
from rustic_ai.core.guild.builders import AgentBuilder
from rustic_ai.core.guild.dsl import AgentSpec
from rustic_ai.llm_agent.react import (
    CompositeToolset,
    ReActAgent,
    ReActAgentConfig,
    ReActRequest,
    ReActResponse,
    ReActStep,
    ReActToolset,
)

from rustic_ai.testing.helpers import wrap_agent_for_testing


# Test tool parameter models
class CalculateParams(BaseModel):
    """Parameters for calculate tool."""

    expression: str


class SearchParams(BaseModel):
    """Parameters for search tool."""

    query: str


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
        with patch.object(agent, "_call_llm", return_value=create_mock_response("The answer is 42.")):
            agent._on_message(
                build_message_from_payload(
                    generator,
                    ReActRequest(query="What is the answer?"),
                )
            )

        assert len(results) == 1
        response = ReActResponse.model_validate(results[0].payload)
        assert response.answer == "The answer is 42."
        assert response.success is True
        assert len(response.trace) == 0  # No tool calls

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

        def mock_call_llm(llm, messages):
            response = responses[call_count[0]]
            call_count[0] += 1
            return response

        with patch.object(agent, "_call_llm", side_effect=mock_call_llm):
            agent._on_message(
                build_message_from_payload(
                    generator,
                    ReActRequest(query="What is 2 + 2?"),
                )
            )

        assert len(results) == 1
        response = ReActResponse.model_validate(results[0].payload)
        assert response.answer == "The result is 4."
        assert response.success is True
        assert len(response.trace) == 1
        assert response.trace[0].action == "calculate"
        assert response.trace[0].observation == "4"


class TestReActModels:
    """Tests for ReAct model classes."""

    def test_react_request(self):
        """Test ReActRequest model."""
        request = ReActRequest(query="Test query")
        assert request.query == "Test query"
        assert request.context is None

        request_with_context = ReActRequest(query="Test query", context={"key": "value"})
        assert request_with_context.context == {"key": "value"}

    def test_react_response(self):
        """Test ReActResponse model."""
        response = ReActResponse(
            answer="Test answer",
            trace=[
                ReActStep(
                    thought="Thinking...",
                    action="test_action",
                    action_input={"arg": "value"},
                    observation="Result",
                )
            ],
            iterations=1,
            success=True,
        )

        assert response.answer == "Test answer"
        assert len(response.trace) == 1
        assert response.iterations == 1
        assert response.success is True

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
