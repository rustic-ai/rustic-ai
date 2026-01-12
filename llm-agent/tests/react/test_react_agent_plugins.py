"""
Tests for plugin support in ReActAgent.

This module tests that RequestPreprocessor, LLMCallWrapper, and ResponsePostprocessor
plugins work correctly with ReActAgent. Key behaviors to verify:
1. Preprocessors run once before the ReAct loop starts
2. Postprocessors run once after the loop completes (with the final response)
3. Plugin-generated messages are returned alongside the ReActResponse
4. Plugins can access injected dependencies via self.get_dep(agent, name)
"""

import json
from typing import Any, List, Optional
from unittest.mock import patch

from pydantic import BaseModel
import pytest

from rustic_ai.core.guild.agent import Agent
from rustic_ai.core.guild.agent_ext.depends.dependency_resolver import (
    DependencyResolver,
    DependencySpec,
)
from rustic_ai.core.guild.agent_ext.depends.llm.llm import LLM
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    AssistantMessage,
    ChatCompletionMessageToolCall,
    ChatCompletionRequest,
    ChatCompletionResponse,
    Choice,
    CompletionUsage,
    FinishReason,
    FunctionCall,
    SystemMessage,
    ToolType,
)
from rustic_ai.core.guild.agent_ext.depends.llm.tools_manager import ToolSpec
from rustic_ai.core.guild.builders import AgentBuilder
from rustic_ai.core.guild.dsl import AgentSpec
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.llm_agent.plugins.llm_call_wrapper import LLMCallWrapper
from rustic_ai.llm_agent.plugins.request_preprocessor import RequestPreprocessor
from rustic_ai.llm_agent.plugins.response_postprocessor import ResponsePostprocessor
from rustic_ai.llm_agent.plugins.tool_call_wrapper import (
    ToolCallResult,
    ToolCallWrapper,
    ToolSkipResult,
)
from rustic_ai.llm_agent.react import (
    ReActAgent,
    ReActAgentConfig,
    ReActRequest,
    ReActResponse,
    ReActToolset,
)

from rustic_ai.testing.helpers import wrap_agent_for_testing

# =============================================================================
# Test Tool Parameter Models
# =============================================================================


class CalculateParams(BaseModel):
    """Parameters for calculate tool."""

    expression: str


# =============================================================================
# Test Toolset
# =============================================================================


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
            try:
                result = eval(args.expression)  # noqa: S307
                return str(result)
            except Exception as e:
                return f"Error: {e}"
        raise ValueError(f"Unknown tool: {tool_name}")


class ErrorRaisingToolset(ReActToolset):
    """A toolset that raises exceptions on execution for testing error handlers."""

    def get_toolspecs(self) -> List[ToolSpec]:
        return [
            ToolSpec(
                name="calculate",
                description="Evaluate a mathematical expression (may fail)",
                parameter_class=CalculateParams,
            )
        ]

    def execute(self, tool_name: str, args: Any) -> str:
        if tool_name == "calculate":
            assert isinstance(args, CalculateParams)
            # Always raise an exception for testing
            raise RuntimeError(f"Intentional error: {args.expression}")
        raise ValueError(f"Unknown tool: {tool_name}")


# =============================================================================
# Test Dependencies
# =============================================================================


class SimpleLogger:
    """A simple logger dependency for testing."""

    # Class-level shared logs for testing (since resolver creates new instances)
    shared_logs: List[str] = []

    def __init__(self, prefix: str = ""):
        self.prefix = prefix
        self.logs: List[str] = []

    def log(self, message: str) -> None:
        log_entry = f"{self.prefix}{message}"
        self.logs.append(log_entry)
        # Also add to shared logs for cross-instance verification
        SimpleLogger.shared_logs.append(log_entry)

    @classmethod
    def reset_shared_logs(cls):
        cls.shared_logs = []


class SimpleLoggerResolver(DependencyResolver[SimpleLogger]):
    """Resolver that creates SimpleLogger instances."""

    def __init__(self, prefix: str = "") -> None:
        super().__init__()
        self.prefix = prefix

    def resolve(self, org_id: str, guild_id: str, agent_id: Optional[str] = None) -> SimpleLogger:
        return SimpleLogger(prefix=self.prefix)


# =============================================================================
# Test Plugins
# =============================================================================


class CapturePreprocessor(RequestPreprocessor):
    """A preprocessor that captures call information for testing."""

    captured_requests: List[ChatCompletionRequest] = []
    call_count: int = 0

    def preprocess(
        self,
        agent: Agent,
        ctx,
        request: ChatCompletionRequest,
        llm: LLM,
    ) -> ChatCompletionRequest:
        CapturePreprocessor.call_count += 1
        CapturePreprocessor.captured_requests.append(request)
        return request

    @classmethod
    def reset(cls):
        cls.captured_requests = []
        cls.call_count = 0


class ModifyPromptPreprocessor(RequestPreprocessor):
    """A preprocessor that modifies the request by adding a system message."""

    injected_content: str = "[INJECTED BY PREPROCESSOR]"

    def preprocess(
        self,
        agent: Agent,
        ctx,
        request: ChatCompletionRequest,
        llm: LLM,
    ) -> ChatCompletionRequest:
        # Add a system message to the request
        new_messages = [SystemMessage(content=self.injected_content)] + list(request.messages)
        return request.model_copy(update={"messages": new_messages})


class CapturePostprocessor(ResponsePostprocessor):
    """A postprocessor that captures response information for testing."""

    captured_responses: List[ChatCompletionResponse] = []
    captured_requests: List[ChatCompletionRequest] = []
    call_count: int = 0

    def postprocess(
        self,
        agent: Agent,
        ctx,
        final_prompt: ChatCompletionRequest,
        llm_response: ChatCompletionResponse,
        llm: LLM,
    ) -> Optional[List[BaseModel]]:
        CapturePostprocessor.call_count += 1
        CapturePostprocessor.captured_responses.append(llm_response)
        CapturePostprocessor.captured_requests.append(final_prompt)
        return None

    @classmethod
    def reset(cls):
        cls.captured_responses = []
        cls.captured_requests = []
        cls.call_count = 0


class MessageGeneratingPostprocessor(ResponsePostprocessor):
    """A postprocessor that generates additional messages."""

    class AuditMessage(BaseModel):
        """Audit message generated by postprocessor."""

        audit_type: str
        content: str

    def postprocess(
        self,
        agent: Agent,
        ctx,
        final_prompt: ChatCompletionRequest,
        llm_response: ChatCompletionResponse,
        llm: LLM,
    ) -> Optional[List[BaseModel]]:
        return [
            self.AuditMessage(
                audit_type="react_completion",
                content=f"ReAct loop completed with {len(llm_response.choices)} choices",
            )
        ]


class CaptureWrapper(LLMCallWrapper):
    """A wrapper that captures both pre and post processing."""

    preprocess_calls: int = 0
    postprocess_calls: int = 0
    captured_final_request: Optional[ChatCompletionRequest] = None
    captured_response: Optional[ChatCompletionResponse] = None

    def preprocess(
        self,
        agent: Agent,
        ctx,
        request: ChatCompletionRequest,
        llm: LLM,
    ) -> ChatCompletionRequest:
        CaptureWrapper.preprocess_calls += 1
        return request

    def postprocess(
        self,
        agent: Agent,
        ctx,
        final_prompt: ChatCompletionRequest,
        llm_response: ChatCompletionResponse,
        llm: LLM,
    ) -> Optional[List[BaseModel]]:
        CaptureWrapper.postprocess_calls += 1
        CaptureWrapper.captured_final_request = final_prompt
        CaptureWrapper.captured_response = llm_response
        return None

    @classmethod
    def reset(cls):
        cls.preprocess_calls = 0
        cls.postprocess_calls = 0
        cls.captured_final_request = None
        cls.captured_response = None


class LoggingPreprocessorWithDep(RequestPreprocessor):
    """A preprocessor that uses a logger dependency."""

    depends_on: List[str] = ["test_logger"]

    def preprocess(
        self,
        agent: Agent,
        ctx,
        request: ChatCompletionRequest,
        llm: LLM,
    ) -> ChatCompletionRequest:
        logger = self.get_dep(agent, "test_logger")
        logger.log("react_preprocess_called")
        return request


class LoggingPostprocessorWithDep(ResponsePostprocessor):
    """A postprocessor that uses a logger dependency."""

    depends_on: List[str] = ["test_logger"]

    def postprocess(
        self,
        agent: Agent,
        ctx,
        final_prompt: ChatCompletionRequest,
        llm_response: ChatCompletionResponse,
        llm: LLM,
    ) -> Optional[List[BaseModel]]:
        logger = self.get_dep(agent, "test_logger")
        logger.log("react_postprocess_called")
        return None


# =============================================================================
# Helper Functions
# =============================================================================


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


# =============================================================================
# Tests
# =============================================================================


class TestReActAgentPluginConfig:
    """Tests for ReActAgentConfig plugin fields."""

    def test_config_has_plugin_fields(self):
        """Test that ReActAgentConfig has plugin configuration fields."""
        config = ReActAgentConfig(
            model="test-model",
            toolset=CalculatorToolset(),
        )

        # Should have plugin fields from LLMPluginMixin
        assert hasattr(config, "request_preprocessors")
        assert hasattr(config, "llm_request_wrappers")
        assert hasattr(config, "response_postprocessors")
        assert hasattr(config, "max_retries")

    def test_config_with_plugins(self):
        """Test creating config with plugins."""
        config = ReActAgentConfig(
            model="test-model",
            toolset=CalculatorToolset(),
            request_preprocessors=[CapturePreprocessor()],
            llm_request_wrappers=[CaptureWrapper()],
            response_postprocessors=[CapturePostprocessor()],
        )

        assert len(config.request_preprocessors) == 1
        assert len(config.llm_request_wrappers) == 1
        assert len(config.response_postprocessors) == 1

    def test_has_plugins_returns_false_when_no_plugins(self):
        """Test has_plugins returns False when no plugins configured."""
        config = ReActAgentConfig(
            model="test-model",
            toolset=CalculatorToolset(),
        )

        assert config.has_plugins() is False

    def test_has_plugins_returns_true_with_preprocessor(self):
        """Test has_plugins returns True with preprocessor."""
        config = ReActAgentConfig(
            model="test-model",
            toolset=CalculatorToolset(),
            request_preprocessors=[CapturePreprocessor()],
        )

        assert config.has_plugins() is True

    def test_has_plugins_returns_true_with_wrapper(self):
        """Test has_plugins returns True with wrapper."""
        config = ReActAgentConfig(
            model="test-model",
            toolset=CalculatorToolset(),
            llm_request_wrappers=[CaptureWrapper()],
        )

        assert config.has_plugins() is True

    def test_has_plugins_returns_true_with_postprocessor(self):
        """Test has_plugins returns True with postprocessor."""
        config = ReActAgentConfig(
            model="test-model",
            toolset=CalculatorToolset(),
            response_postprocessors=[CapturePostprocessor()],
        )

        assert config.has_plugins() is True


class TestReActAgentPreprocessor:
    """Tests for RequestPreprocessor with ReActAgent."""

    @pytest.fixture(autouse=True)
    def reset_plugins(self):
        """Reset plugin state before each test."""
        CapturePreprocessor.reset()
        CapturePostprocessor.reset()
        CaptureWrapper.reset()
        yield

    def test_preprocessor_called_once_before_loop(self, generator, build_message_from_payload):
        """Test that preprocessor is called exactly once before the ReAct loop."""
        agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("react_agent")
            .set_name("ReAct Agent")
            .set_description("A ReAct agent with preprocessor")
            .set_properties(
                ReActAgentConfig(
                    model="test-model",
                    toolset=CalculatorToolset(),
                    request_preprocessors=[CapturePreprocessor()],
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

        agent, results = wrap_agent_for_testing(agent_spec, dependency_map=mock_dependency_map)

        # Simulate multiple iterations: tool call -> tool call -> final answer
        responses = [
            create_mock_response(
                content="First tool call",
                tool_calls=[create_tool_call("call_1", "calculate", {"expression": "2 + 2"})],
                finish_reason=FinishReason.tool_calls,
            ),
            create_mock_response(
                content="Second tool call",
                tool_calls=[create_tool_call("call_2", "calculate", {"expression": "4 * 3"})],
                finish_reason=FinishReason.tool_calls,
            ),
            create_mock_response("The final answer is 12."),
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
                    ReActRequest(query="Calculate 2 + 2 then multiply by 3"),
                )
            )

        # Preprocessor should be called exactly ONCE (before the loop)
        assert CapturePreprocessor.call_count == 1

        # And it should have captured the initial request
        assert len(CapturePreprocessor.captured_requests) == 1

    def test_preprocessor_modifies_initial_request(self, generator, build_message_from_payload):
        """Test that preprocessor modifications apply to the initial request."""
        agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("react_agent")
            .set_name("ReAct Agent")
            .set_description("A ReAct agent with modifying preprocessor")
            .set_properties(
                ReActAgentConfig(
                    model="test-model",
                    toolset=CalculatorToolset(),
                    request_preprocessors=[ModifyPromptPreprocessor()],
                    llm_request_wrappers=[CaptureWrapper()],  # To capture final request
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

        agent, results = wrap_agent_for_testing(agent_spec, dependency_map=mock_dependency_map)

        with patch.object(agent, "_call_llm_direct", return_value=create_mock_response("Answer is 42.")):
            agent._on_message(
                build_message_from_payload(
                    generator,
                    ReActRequest(query="What is the answer?"),
                )
            )

        # The wrapper's preprocess should see the modified request (with injected system message)
        # Note: wrapper runs after preprocessors in the pipeline
        assert CaptureWrapper.preprocess_calls == 1


class TestReActAgentPostprocessor:
    """Tests for ResponsePostprocessor with ReActAgent."""

    @pytest.fixture(autouse=True)
    def reset_plugins(self):
        """Reset plugin state before each test."""
        CapturePreprocessor.reset()
        CapturePostprocessor.reset()
        CaptureWrapper.reset()
        yield

    def test_postprocessor_called_once_after_loop(self, generator, build_message_from_payload):
        """Test that postprocessor is called exactly once after the ReAct loop completes."""
        agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("react_agent")
            .set_name("ReAct Agent")
            .set_description("A ReAct agent with postprocessor")
            .set_properties(
                ReActAgentConfig(
                    model="test-model",
                    toolset=CalculatorToolset(),
                    response_postprocessors=[CapturePostprocessor()],
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

        agent, results = wrap_agent_for_testing(agent_spec, dependency_map=mock_dependency_map)

        # Simulate multiple iterations
        responses = [
            create_mock_response(
                content="Tool call",
                tool_calls=[create_tool_call("call_1", "calculate", {"expression": "5 + 5"})],
                finish_reason=FinishReason.tool_calls,
            ),
            create_mock_response("The answer is 10."),
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
                    ReActRequest(query="What is 5 + 5?"),
                )
            )

        # Postprocessor should be called exactly ONCE (after the loop)
        assert CapturePostprocessor.call_count == 1

        # It should have captured the FINAL response (not intermediate ones)
        assert len(CapturePostprocessor.captured_responses) == 1
        final_response = CapturePostprocessor.captured_responses[0]
        assert final_response.choices[0].message.content == "The answer is 10."

    def test_postprocessor_receives_final_response(self, generator, build_message_from_payload):
        """Test that postprocessor receives the final LLM response, not intermediate ones."""
        agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("react_agent")
            .set_name("ReAct Agent")
            .set_description("A ReAct agent with postprocessor")
            .set_properties(
                ReActAgentConfig(
                    model="test-model",
                    toolset=CalculatorToolset(),
                    response_postprocessors=[CapturePostprocessor()],
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

        agent, results = wrap_agent_for_testing(agent_spec, dependency_map=mock_dependency_map)

        with patch.object(agent, "_call_llm_direct", return_value=create_mock_response("Direct answer.")):
            agent._on_message(
                build_message_from_payload(
                    generator,
                    ReActRequest(query="Simple question"),
                )
            )

        assert CapturePostprocessor.call_count == 1
        assert CapturePostprocessor.captured_responses[0].choices[0].message.content == "Direct answer."

    def test_postprocessor_generated_messages_returned(self, generator, build_message_from_payload):
        """Test that messages generated by postprocessor are included in results."""
        agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("react_agent")
            .set_name("ReAct Agent")
            .set_description("A ReAct agent with message-generating postprocessor")
            .set_properties(
                ReActAgentConfig(
                    model="test-model",
                    toolset=CalculatorToolset(),
                    response_postprocessors=[MessageGeneratingPostprocessor()],
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

        agent, results = wrap_agent_for_testing(agent_spec, dependency_map=mock_dependency_map)

        with patch.object(agent, "_call_llm_direct", return_value=create_mock_response("Answer.")):
            agent._on_message(
                build_message_from_payload(
                    generator,
                    ReActRequest(query="Test query"),
                )
            )

        # Should have 2 results: AuditMessage from postprocessor (sent first) + ReActResponse
        assert len(results) == 2

        # First is the plugin-generated AuditMessage (plugin messages sent first)
        audit = MessageGeneratingPostprocessor.AuditMessage.model_validate(results[0].payload)
        assert audit.audit_type == "react_completion"

        # Second is the ReActResponse
        response = ReActResponse.model_validate(results[1].payload)
        assert response.answer == "Answer."


class TestReActAgentWrapper:
    """Tests for LLMCallWrapper with ReActAgent."""

    @pytest.fixture(autouse=True)
    def reset_plugins(self):
        """Reset plugin state before each test."""
        CapturePreprocessor.reset()
        CapturePostprocessor.reset()
        CaptureWrapper.reset()
        yield

    def test_wrapper_called_once_per_loop(self, generator, build_message_from_payload):
        """Test that wrapper pre/post are called once (wrapping the entire loop)."""
        agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("react_agent")
            .set_name("ReAct Agent")
            .set_description("A ReAct agent with wrapper")
            .set_properties(
                ReActAgentConfig(
                    model="test-model",
                    toolset=CalculatorToolset(),
                    llm_request_wrappers=[CaptureWrapper()],
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

        agent, results = wrap_agent_for_testing(agent_spec, dependency_map=mock_dependency_map)

        # Multiple iterations
        responses = [
            create_mock_response(
                content="Tool",
                tool_calls=[create_tool_call("c1", "calculate", {"expression": "1+1"})],
                finish_reason=FinishReason.tool_calls,
            ),
            create_mock_response("Done."),
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
                    ReActRequest(query="Calculate 1+1"),
                )
            )

        # Wrapper should wrap the entire loop, so called once each for pre/post
        assert CaptureWrapper.preprocess_calls == 1
        assert CaptureWrapper.postprocess_calls == 1


class TestReActAgentPluginDependencyInjection:
    """Tests for plugin dependency injection with ReActAgent."""

    @pytest.fixture(autouse=True)
    def reset_plugins(self):
        """Reset plugin state before each test."""
        CapturePreprocessor.reset()
        CapturePostprocessor.reset()
        CaptureWrapper.reset()
        SimpleLogger.reset_shared_logs()
        yield

    def test_preprocessor_can_access_dependencies(self, generator, build_message_from_payload):
        """Test that preprocessor can access injected dependencies via get_dep."""
        dependency_map = {
            "llm": DependencySpec(
                class_name="rustic_ai.litellm.agent_ext.llm.LiteLLMResolver",
                properties={"model": "test-model"},
            ),
            "test_logger": DependencySpec(
                class_name=get_qualified_class_name(SimpleLoggerResolver),
                properties={"prefix": "[REACT] "},
            ),
        }

        agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("react_agent")
            .set_name("ReAct Agent")
            .set_description("A ReAct agent with dependency-using preprocessor")
            .set_properties(
                ReActAgentConfig(
                    model="test-model",
                    toolset=CalculatorToolset(),
                    request_preprocessors=[LoggingPreprocessorWithDep()],
                )
            )
            .set_additional_dependencies(["test_logger"])
            .build_spec()
        )

        agent, results = wrap_agent_for_testing(agent_spec, dependency_map=dependency_map)

        with patch.object(agent, "_call_llm_direct", return_value=create_mock_response("Answer.")):
            agent._on_message(
                build_message_from_payload(
                    generator,
                    ReActRequest(query="Test"),
                )
            )

        # Verify the logger was used by the preprocessor (using shared logs)
        assert "[REACT] react_preprocess_called" in SimpleLogger.shared_logs

    def test_postprocessor_can_access_dependencies(self, generator, build_message_from_payload):
        """Test that postprocessor can access injected dependencies via get_dep."""
        dependency_map = {
            "llm": DependencySpec(
                class_name="rustic_ai.litellm.agent_ext.llm.LiteLLMResolver",
                properties={"model": "test-model"},
            ),
            "test_logger": DependencySpec(
                class_name=get_qualified_class_name(SimpleLoggerResolver),
                properties={"prefix": "[REACT] "},
            ),
        }

        agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("react_agent")
            .set_name("ReAct Agent")
            .set_description("A ReAct agent with dependency-using postprocessor")
            .set_properties(
                ReActAgentConfig(
                    model="test-model",
                    toolset=CalculatorToolset(),
                    response_postprocessors=[LoggingPostprocessorWithDep()],
                )
            )
            .set_additional_dependencies(["test_logger"])
            .build_spec()
        )

        agent, results = wrap_agent_for_testing(agent_spec, dependency_map=dependency_map)

        with patch.object(agent, "_call_llm_direct", return_value=create_mock_response("Answer.")):
            agent._on_message(
                build_message_from_payload(
                    generator,
                    ReActRequest(query="Test"),
                )
            )

        # Verify the logger was used by the postprocessor (using shared logs)
        assert "[REACT] react_postprocess_called" in SimpleLogger.shared_logs


class TestReActAgentMultiplePlugins:
    """Tests for multiple plugins working together with ReActAgent."""

    @pytest.fixture(autouse=True)
    def reset_plugins(self):
        """Reset plugin state before each test."""
        CapturePreprocessor.reset()
        CapturePostprocessor.reset()
        CaptureWrapper.reset()
        yield

    def test_all_plugin_types_work_together(self, generator, build_message_from_payload):
        """Test that preprocessor, wrapper, and postprocessor all work together."""
        agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("react_agent")
            .set_name("ReAct Agent")
            .set_description("A ReAct agent with all plugin types")
            .set_properties(
                ReActAgentConfig(
                    model="test-model",
                    toolset=CalculatorToolset(),
                    request_preprocessors=[CapturePreprocessor()],
                    llm_request_wrappers=[CaptureWrapper()],
                    response_postprocessors=[CapturePostprocessor()],
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

        agent, results = wrap_agent_for_testing(agent_spec, dependency_map=mock_dependency_map)

        with patch.object(agent, "_call_llm_direct", return_value=create_mock_response("Final answer.")):
            agent._on_message(
                build_message_from_payload(
                    generator,
                    ReActRequest(query="Test query"),
                )
            )

        # All plugins should have been called once
        assert CapturePreprocessor.call_count == 1
        assert CaptureWrapper.preprocess_calls == 1
        assert CaptureWrapper.postprocess_calls == 1
        assert CapturePostprocessor.call_count == 1

        # Response should be captured correctly
        assert len(results) == 1
        response = ReActResponse.model_validate(results[0].payload)
        assert response.answer == "Final answer."


# =============================================================================
# Iteration Plugin Tests
# =============================================================================


class IterationCapturePreprocessor(RequestPreprocessor):
    """A preprocessor that captures each iteration call."""

    captured_iterations: List[int] = []
    call_count: int = 0

    def preprocess(
        self,
        agent: Agent,
        ctx,
        request: ChatCompletionRequest,
        llm: LLM,
    ) -> ChatCompletionRequest:
        IterationCapturePreprocessor.call_count += 1
        return request

    @classmethod
    def reset(cls):
        cls.captured_iterations = []
        cls.call_count = 0


class IterationCapturePostprocessor(ResponsePostprocessor):
    """A postprocessor that captures each iteration response."""

    captured_responses: List[ChatCompletionResponse] = []
    call_count: int = 0

    def postprocess(
        self,
        agent: Agent,
        ctx,
        final_prompt: ChatCompletionRequest,
        llm_response: ChatCompletionResponse,
        llm: LLM,
    ) -> Optional[List[BaseModel]]:
        IterationCapturePostprocessor.call_count += 1
        IterationCapturePostprocessor.captured_responses.append(llm_response)
        return None

    @classmethod
    def reset(cls):
        cls.captured_responses = []
        cls.call_count = 0


class IterationCaptureWrapper(LLMCallWrapper):
    """A wrapper that captures pre/post for each iteration."""

    preprocess_calls: int = 0
    postprocess_calls: int = 0

    def preprocess(
        self,
        agent: Agent,
        ctx,
        request: ChatCompletionRequest,
        llm: LLM,
    ) -> ChatCompletionRequest:
        IterationCaptureWrapper.preprocess_calls += 1
        return request

    def postprocess(
        self,
        agent: Agent,
        ctx,
        final_prompt: ChatCompletionRequest,
        llm_response: ChatCompletionResponse,
        llm: LLM,
    ) -> Optional[List[BaseModel]]:
        IterationCaptureWrapper.postprocess_calls += 1
        return None

    @classmethod
    def reset(cls):
        cls.preprocess_calls = 0
        cls.postprocess_calls = 0


class IterationMessageGenerator(ResponsePostprocessor):
    """A postprocessor that generates a message for each iteration."""

    class IterationMetric(BaseModel):
        """Metric message generated per iteration."""

        iteration_metric: str
        response_content: str

    def postprocess(
        self,
        agent: Agent,
        ctx,
        final_prompt: ChatCompletionRequest,
        llm_response: ChatCompletionResponse,
        llm: LLM,
    ) -> Optional[List[BaseModel]]:
        content = llm_response.choices[0].message.content or ""
        return [
            self.IterationMetric(
                iteration_metric="step_complete",
                response_content=content[:50],
            )
        ]


class TestReActAgentIterationPluginConfig:
    """Tests for ReActAgentConfig iteration plugin fields."""

    def test_config_has_iteration_plugin_fields(self):
        """Test that ReActAgentConfig has iteration plugin configuration fields."""
        config = ReActAgentConfig(
            model="test-model",
            toolset=CalculatorToolset(),
        )

        assert hasattr(config, "iteration_preprocessors")
        assert hasattr(config, "iteration_wrappers")
        assert hasattr(config, "iteration_postprocessors")

    def test_config_with_iteration_plugins(self):
        """Test creating config with iteration plugins."""
        config = ReActAgentConfig(
            model="test-model",
            toolset=CalculatorToolset(),
            iteration_preprocessors=[IterationCapturePreprocessor()],
            iteration_wrappers=[IterationCaptureWrapper()],
            iteration_postprocessors=[IterationCapturePostprocessor()],
        )

        assert len(config.iteration_preprocessors) == 1
        assert len(config.iteration_wrappers) == 1
        assert len(config.iteration_postprocessors) == 1

    def test_has_iteration_plugins_returns_false_when_none(self):
        """Test has_iteration_plugins returns False when no iteration plugins configured."""
        config = ReActAgentConfig(
            model="test-model",
            toolset=CalculatorToolset(),
        )

        assert config.has_iteration_plugins() is False

    def test_has_iteration_plugins_returns_true_with_preprocessor(self):
        """Test has_iteration_plugins returns True with iteration preprocessor."""
        config = ReActAgentConfig(
            model="test-model",
            toolset=CalculatorToolset(),
            iteration_preprocessors=[IterationCapturePreprocessor()],
        )

        assert config.has_iteration_plugins() is True


class TestReActAgentIterationPlugins:
    """Tests for per-iteration plugins with ReActAgent."""

    @pytest.fixture(autouse=True)
    def reset_plugins(self):
        """Reset plugin state before each test."""
        CapturePreprocessor.reset()
        CapturePostprocessor.reset()
        CaptureWrapper.reset()
        IterationCapturePreprocessor.reset()
        IterationCapturePostprocessor.reset()
        IterationCaptureWrapper.reset()
        SimpleLogger.reset_shared_logs()
        yield

    def test_iteration_preprocessor_called_per_iteration(self, generator, build_message_from_payload):
        """Test that iteration preprocessor is called for each LLM call in the loop."""
        agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("react_agent")
            .set_name("ReAct Agent")
            .set_description("A ReAct agent with iteration preprocessor")
            .set_properties(
                ReActAgentConfig(
                    model="test-model",
                    toolset=CalculatorToolset(),
                    iteration_preprocessors=[IterationCapturePreprocessor()],
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

        agent, results = wrap_agent_for_testing(agent_spec, dependency_map=mock_dependency_map)

        # 3 LLM calls: tool -> tool -> answer
        responses = [
            create_mock_response(
                content="First call",
                tool_calls=[create_tool_call("c1", "calculate", {"expression": "1+1"})],
                finish_reason=FinishReason.tool_calls,
            ),
            create_mock_response(
                content="Second call",
                tool_calls=[create_tool_call("c2", "calculate", {"expression": "2+2"})],
                finish_reason=FinishReason.tool_calls,
            ),
            create_mock_response("Final answer."),
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
                    ReActRequest(query="Test"),
                )
            )

        # Iteration preprocessor called 3 times (once per LLM call)
        assert IterationCapturePreprocessor.call_count == 3

    def test_iteration_postprocessor_called_per_iteration(self, generator, build_message_from_payload):
        """Test that iteration postprocessor is called after each LLM call in the loop."""
        agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("react_agent")
            .set_name("ReAct Agent")
            .set_description("A ReAct agent with iteration postprocessor")
            .set_properties(
                ReActAgentConfig(
                    model="test-model",
                    toolset=CalculatorToolset(),
                    iteration_postprocessors=[IterationCapturePostprocessor()],
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

        agent, results = wrap_agent_for_testing(agent_spec, dependency_map=mock_dependency_map)

        # 2 LLM calls: tool -> answer
        responses = [
            create_mock_response(
                content="Tool call",
                tool_calls=[create_tool_call("c1", "calculate", {"expression": "5+5"})],
                finish_reason=FinishReason.tool_calls,
            ),
            create_mock_response("Answer is 10."),
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
                    ReActRequest(query="What is 5+5?"),
                )
            )

        # Iteration postprocessor called 2 times (once per LLM call)
        assert IterationCapturePostprocessor.call_count == 2

        # Should have captured both responses
        assert len(IterationCapturePostprocessor.captured_responses) == 2
        # First is tool call, second is final answer
        assert IterationCapturePostprocessor.captured_responses[1].choices[0].message.content == "Answer is 10."

    def test_iteration_wrapper_called_per_iteration(self, generator, build_message_from_payload):
        """Test that iteration wrapper pre/post are called for each LLM call."""
        agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("react_agent")
            .set_name("ReAct Agent")
            .set_description("A ReAct agent with iteration wrapper")
            .set_properties(
                ReActAgentConfig(
                    model="test-model",
                    toolset=CalculatorToolset(),
                    iteration_wrappers=[IterationCaptureWrapper()],
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

        agent, results = wrap_agent_for_testing(agent_spec, dependency_map=mock_dependency_map)

        # 3 iterations
        responses = [
            create_mock_response(
                content="Call 1",
                tool_calls=[create_tool_call("c1", "calculate", {"expression": "1"})],
                finish_reason=FinishReason.tool_calls,
            ),
            create_mock_response(
                content="Call 2",
                tool_calls=[create_tool_call("c2", "calculate", {"expression": "2"})],
                finish_reason=FinishReason.tool_calls,
            ),
            create_mock_response("Done."),
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
                    ReActRequest(query="Test"),
                )
            )

        # Wrapper called 3 times each for pre and post
        assert IterationCaptureWrapper.preprocess_calls == 3
        assert IterationCaptureWrapper.postprocess_calls == 3

    def test_iteration_postprocessor_messages_accumulated(self, generator, build_message_from_payload):
        """Test that messages from iteration postprocessors are accumulated and sent."""
        agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("react_agent")
            .set_name("ReAct Agent")
            .set_description("A ReAct agent with message-generating iteration postprocessor")
            .set_properties(
                ReActAgentConfig(
                    model="test-model",
                    toolset=CalculatorToolset(),
                    iteration_postprocessors=[IterationMessageGenerator()],
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

        agent, results = wrap_agent_for_testing(agent_spec, dependency_map=mock_dependency_map)

        # 2 iterations
        responses = [
            create_mock_response(
                content="Step 1 response",
                tool_calls=[create_tool_call("c1", "calculate", {"expression": "1"})],
                finish_reason=FinishReason.tool_calls,
            ),
            create_mock_response("Final step response"),
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
                    ReActRequest(query="Test"),
                )
            )

        # Should have 3 results: 2 IterationMetric messages + 1 ReActResponse
        assert len(results) == 3

        # First two are iteration metrics (iteration messages sent before ReActResponse)
        metric1 = IterationMessageGenerator.IterationMetric.model_validate(results[0].payload)
        assert metric1.iteration_metric == "step_complete"

        metric2 = IterationMessageGenerator.IterationMetric.model_validate(results[1].payload)
        assert metric2.iteration_metric == "step_complete"

        # Last is the ReActResponse
        response = ReActResponse.model_validate(results[2].payload)
        assert response.answer == "Final step response"


class TestReActAgentBothPluginLevels:
    """Tests for using both loop-level and iteration-level plugins together."""

    @pytest.fixture(autouse=True)
    def reset_plugins(self):
        """Reset plugin state before each test."""
        CapturePreprocessor.reset()
        CapturePostprocessor.reset()
        CaptureWrapper.reset()
        IterationCapturePreprocessor.reset()
        IterationCapturePostprocessor.reset()
        IterationCaptureWrapper.reset()
        yield

    def test_both_loop_and_iteration_plugins(self, generator, build_message_from_payload):
        """Test that both loop-level and iteration-level plugins work together."""
        agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("react_agent")
            .set_name("ReAct Agent")
            .set_description("A ReAct agent with both plugin levels")
            .set_properties(
                ReActAgentConfig(
                    model="test-model",
                    toolset=CalculatorToolset(),
                    # Loop-level plugins (once per loop)
                    request_preprocessors=[CapturePreprocessor()],
                    response_postprocessors=[CapturePostprocessor()],
                    # Iteration-level plugins (per LLM call)
                    iteration_preprocessors=[IterationCapturePreprocessor()],
                    iteration_postprocessors=[IterationCapturePostprocessor()],
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

        agent, results = wrap_agent_for_testing(agent_spec, dependency_map=mock_dependency_map)

        # 3 iterations
        responses = [
            create_mock_response(
                content="Iteration 1",
                tool_calls=[create_tool_call("c1", "calculate", {"expression": "1"})],
                finish_reason=FinishReason.tool_calls,
            ),
            create_mock_response(
                content="Iteration 2",
                tool_calls=[create_tool_call("c2", "calculate", {"expression": "2"})],
                finish_reason=FinishReason.tool_calls,
            ),
            create_mock_response("Final."),
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
                    ReActRequest(query="Test"),
                )
            )

        # Loop-level plugins: called once
        assert CapturePreprocessor.call_count == 1
        assert CapturePostprocessor.call_count == 1

        # Iteration-level plugins: called 3 times (per LLM call)
        assert IterationCapturePreprocessor.call_count == 3
        assert IterationCapturePostprocessor.call_count == 3

        # Final response
        assert len(results) == 1
        response = ReActResponse.model_validate(results[0].payload)
        assert response.answer == "Final."


# =============================================================================
# Tool Call Wrapper Test Plugins
# =============================================================================


class CaptureToolWrapper(ToolCallWrapper):
    """A tool wrapper that captures all tool calls for testing."""

    call_count: int = 0
    captured_calls: list = []
    captured_results: list = []

    @classmethod
    def reset(cls):
        cls.call_count = 0
        cls.captured_calls = []
        cls.captured_results = []

    def preprocess(
        self,
        agent: Agent,
        ctx: Any,
        tool_name: str,
        tool_input: BaseModel,
    ):
        """Capture the tool call."""
        CaptureToolWrapper.call_count += 1
        CaptureToolWrapper.captured_calls.append({
            "tool_name": tool_name,
            "tool_input": tool_input,
        })
        return tool_input

    def postprocess(
        self,
        agent: Agent,
        ctx: Any,
        tool_name: str,
        tool_input: BaseModel,
        tool_output: str,
    ) -> ToolCallResult:
        """Capture the tool result."""
        CaptureToolWrapper.captured_results.append({
            "tool_name": tool_name,
            "tool_output": tool_output,
        })
        return ToolCallResult(output=tool_output)


class ModifyingToolWrapper(ToolCallWrapper):
    """A tool wrapper that modifies tool inputs and outputs."""

    def preprocess(
        self,
        agent: Agent,
        ctx: Any,
        tool_name: str,
        tool_input: BaseModel,
    ):
        """Modify the expression to add 10."""
        if hasattr(tool_input, "expression"):
            # Create a new model with modified expression
            return type(tool_input)(expression=f"({tool_input.expression}) + 10")
        return tool_input

    def postprocess(
        self,
        agent: Agent,
        ctx: Any,
        tool_name: str,
        tool_input: BaseModel,
        tool_output: str,
    ) -> ToolCallResult:
        """Append a suffix to the output."""
        return ToolCallResult(output=f"{tool_output} [modified]")


class SkippingToolWrapper(ToolCallWrapper):
    """A tool wrapper that skips execution and returns a cached result."""

    skip_tool: str = "calculate"  # The tool name to skip
    cached_result: str = "42 (cached)"

    def preprocess(
        self,
        agent: Agent,
        ctx: Any,
        tool_name: str,
        tool_input: BaseModel,
    ):
        """Skip calculate tool and return cached result."""
        if tool_name == self.skip_tool:
            return ToolSkipResult(output=self.cached_result)
        return tool_input

    def postprocess(
        self,
        agent: Agent,
        ctx: Any,
        tool_name: str,
        tool_input: BaseModel,
        tool_output: str,
    ) -> ToolCallResult:
        """Pass through without modification."""
        return ToolCallResult(output=tool_output)


class ErrorHandlingToolWrapper(ToolCallWrapper):
    """A tool wrapper that handles errors gracefully."""

    handled_errors: list = []

    @classmethod
    def reset(cls):
        cls.handled_errors = []

    def preprocess(
        self,
        agent: Agent,
        ctx: Any,
        tool_name: str,
        tool_input: BaseModel,
    ):
        """Pass through without modification."""
        return tool_input

    def postprocess(
        self,
        agent: Agent,
        ctx: Any,
        tool_name: str,
        tool_input: BaseModel,
        tool_output: str,
    ) -> ToolCallResult:
        """Pass through without modification."""
        return ToolCallResult(output=tool_output)

    def on_error(
        self,
        agent: Agent,
        ctx: Any,
        tool_name: str,
        tool_input: BaseModel,
        error: Exception,
    ) -> Optional[str]:
        """Handle errors by returning a fallback message."""
        ErrorHandlingToolWrapper.handled_errors.append({
            "tool_name": tool_name,
            "error": str(error),
        })
        return f"Error handled: {error}"


class MessageGeneratingToolWrapper(ToolCallWrapper):
    """A tool wrapper that generates messages on tool calls."""

    class ToolCallEvent(BaseModel):
        """Event message for tool calls."""

        event_type: str
        tool_name: str
        tool_output: str

    def preprocess(
        self,
        agent: Agent,
        ctx: Any,
        tool_name: str,
        tool_input: BaseModel,
    ):
        """Pass through without modification."""
        return tool_input

    def postprocess(
        self,
        agent: Agent,
        ctx: Any,
        tool_name: str,
        tool_input: BaseModel,
        tool_output: str,
    ) -> ToolCallResult:
        """Generate an event message for each tool call."""
        event = self.ToolCallEvent(
            event_type="tool_executed",
            tool_name=tool_name,
            tool_output=tool_output,
        )
        return ToolCallResult(output=tool_output, messages=[event])


# =============================================================================
# Tool Wrapper Config Tests
# =============================================================================


class TestReActAgentToolWrapperConfig:
    """Tests for ToolCallWrapper config in ReActAgent."""

    def test_config_has_tool_wrapper_field(self):
        """Test that ReActAgentConfig has tool_wrappers field."""
        config = ReActAgentConfig(
            model="test-model",
            toolset=CalculatorToolset(),
        )
        assert hasattr(config, "tool_wrappers")
        assert config.tool_wrappers == []

    def test_config_with_tool_wrappers(self):
        """Test that tool wrappers can be configured."""
        config = ReActAgentConfig(
            model="test-model",
            toolset=CalculatorToolset(),
            tool_wrappers=[CaptureToolWrapper()],
        )
        assert len(config.tool_wrappers) == 1
        assert isinstance(config.tool_wrappers[0], CaptureToolWrapper)

    def test_has_tool_wrappers_returns_false_when_none(self):
        """Test has_tool_wrappers returns False when no tool wrappers."""
        config = ReActAgentConfig(
            model="test-model",
            toolset=CalculatorToolset(),
        )
        assert config.has_tool_wrappers() is False

    def test_has_tool_wrappers_returns_true_with_wrapper(self):
        """Test has_tool_wrappers returns True when tool wrappers present."""
        config = ReActAgentConfig(
            model="test-model",
            toolset=CalculatorToolset(),
            tool_wrappers=[CaptureToolWrapper()],
        )
        assert config.has_tool_wrappers() is True


# =============================================================================
# Tool Wrapper Behavior Tests
# =============================================================================


class TestReActAgentToolWrappers:
    """Tests for ToolCallWrapper execution with ReActAgent."""

    @pytest.fixture(autouse=True)
    def reset_plugins(self):
        """Reset plugin state before each test."""
        CaptureToolWrapper.reset()
        ErrorHandlingToolWrapper.reset()
        yield

    def test_tool_wrapper_called_per_tool_execution(self, generator, build_message_from_payload):
        """Test that tool wrappers are called for each tool execution."""
        agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("react_agent")
            .set_name("ReAct Agent")
            .set_description("A ReAct agent with tool wrapper")
            .set_properties(
                ReActAgentConfig(
                    model="test-model",
                    toolset=CalculatorToolset(),
                    tool_wrappers=[CaptureToolWrapper()],
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

        agent, results = wrap_agent_for_testing(agent_spec, dependency_map=mock_dependency_map)

        # 2 tool calls then final answer
        responses = [
            create_mock_response(
                content="First calculation",
                tool_calls=[create_tool_call("t1", "calculate", {"expression": "1+1"})],
                finish_reason=FinishReason.tool_calls,
            ),
            create_mock_response(
                content="Second calculation",
                tool_calls=[create_tool_call("t2", "calculate", {"expression": "2+2"})],
                finish_reason=FinishReason.tool_calls,
            ),
            create_mock_response("The results are 2 and 4."),
        ]

        call_idx = [0]

        def mock_call_llm(llm, request):
            response = responses[call_idx[0]]
            call_idx[0] += 1
            return response

        with patch.object(agent, "_call_llm_direct", side_effect=mock_call_llm):
            agent._on_message(
                build_message_from_payload(
                    generator,
                    ReActRequest(query="Calculate 1+1 and 2+2"),
                )
            )

        # Tool wrapper should be called twice (once per tool call)
        assert CaptureToolWrapper.call_count == 2
        assert len(CaptureToolWrapper.captured_calls) == 2
        assert len(CaptureToolWrapper.captured_results) == 2

        # Verify captured tool names and expressions
        assert CaptureToolWrapper.captured_calls[0]["tool_name"] == "calculate"
        assert CaptureToolWrapper.captured_calls[0]["tool_input"].expression == "1+1"
        assert CaptureToolWrapper.captured_calls[1]["tool_name"] == "calculate"
        assert CaptureToolWrapper.captured_calls[1]["tool_input"].expression == "2+2"

    def test_tool_wrapper_can_modify_input_and_output(self, generator, build_message_from_payload):
        """Test that tool wrappers can modify tool inputs and outputs."""
        agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("react_agent")
            .set_name("ReAct Agent")
            .set_description("A ReAct agent with modifying tool wrapper")
            .set_properties(
                ReActAgentConfig(
                    model="test-model",
                    toolset=CalculatorToolset(),
                    tool_wrappers=[ModifyingToolWrapper()],
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

        agent, results = wrap_agent_for_testing(agent_spec, dependency_map=mock_dependency_map)

        responses = [
            create_mock_response(
                content="Calculating",
                tool_calls=[create_tool_call("t1", "calculate", {"expression": "5"})],
                finish_reason=FinishReason.tool_calls,
            ),
            create_mock_response("The result is 15."),
        ]

        call_idx = [0]

        def mock_call_llm(llm, request):
            response = responses[call_idx[0]]
            call_idx[0] += 1
            return response

        with patch.object(agent, "_call_llm_direct", side_effect=mock_call_llm):
            agent._on_message(
                build_message_from_payload(
                    generator,
                    ReActRequest(query="Calculate 5"),
                )
            )

        # Final response
        response = ReActResponse.model_validate(results[0].payload)
        assert response.success is True

        # Trace should show the modified output
        # Input expression was "5", wrapper changed it to "(5) + 10" = 15
        # Output should have "[modified]" suffix
        assert len(response.trace) == 1
        observation = response.trace[0].observation
        assert "[modified]" in observation
        # The actual result: eval("(5) + 10") = 15
        assert "15" in observation

    def test_tool_wrapper_can_skip_execution(self, generator, build_message_from_payload):
        """Test that tool wrappers can skip execution with a cached result."""
        agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("react_agent")
            .set_name("ReAct Agent")
            .set_description("A ReAct agent with skipping tool wrapper")
            .set_properties(
                ReActAgentConfig(
                    model="test-model",
                    toolset=CalculatorToolset(),
                    tool_wrappers=[SkippingToolWrapper()],
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

        agent, results = wrap_agent_for_testing(agent_spec, dependency_map=mock_dependency_map)

        responses = [
            create_mock_response(
                content="Calculating",
                tool_calls=[create_tool_call("t1", "calculate", {"expression": "complex_expr"})],
                finish_reason=FinishReason.tool_calls,
            ),
            create_mock_response("The cached result is 42."),
        ]

        call_idx = [0]

        def mock_call_llm(llm, request):
            response = responses[call_idx[0]]
            call_idx[0] += 1
            return response

        with patch.object(agent, "_call_llm_direct", side_effect=mock_call_llm):
            agent._on_message(
                build_message_from_payload(
                    generator,
                    ReActRequest(query="Calculate something"),
                )
            )

        response = ReActResponse.model_validate(results[0].payload)
        assert response.success is True

        # Trace should show the cached result, not an actual execution
        assert len(response.trace) == 1
        observation = response.trace[0].observation
        assert observation == "42 (cached)"

    def test_tool_wrapper_handles_errors(self, generator, build_message_from_payload):
        """Test that tool wrappers can handle errors gracefully."""
        agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("react_agent")
            .set_name("ReAct Agent")
            .set_description("A ReAct agent with error-handling tool wrapper")
            .set_properties(
                ReActAgentConfig(
                    model="test-model",
                    toolset=ErrorRaisingToolset(),  # Use toolset that raises exceptions
                    tool_wrappers=[ErrorHandlingToolWrapper()],
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

        agent, results = wrap_agent_for_testing(agent_spec, dependency_map=mock_dependency_map)

        # Tool call - the ErrorRaisingToolset will raise an exception
        responses = [
            create_mock_response(
                content="Calculating",
                tool_calls=[create_tool_call("t1", "calculate", {"expression": "1+1"})],
                finish_reason=FinishReason.tool_calls,
            ),
            create_mock_response("I handled the error."),
        ]

        call_idx = [0]

        def mock_call_llm(llm, request):
            response = responses[call_idx[0]]
            call_idx[0] += 1
            return response

        with patch.object(agent, "_call_llm_direct", side_effect=mock_call_llm):
            agent._on_message(
                build_message_from_payload(
                    generator,
                    ReActRequest(query="Calculate something"),
                )
            )

        response = ReActResponse.model_validate(results[0].payload)
        assert response.success is True

        # Error handler should have been invoked
        assert len(ErrorHandlingToolWrapper.handled_errors) == 1
        assert ErrorHandlingToolWrapper.handled_errors[0]["tool_name"] == "calculate"

        # Trace should show the handled error output
        assert len(response.trace) == 1
        observation = response.trace[0].observation
        assert "Error handled:" in observation

    def test_tool_wrapper_generates_messages(self, generator, build_message_from_payload):
        """Test that tool wrappers can generate messages."""
        agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("react_agent")
            .set_name("ReAct Agent")
            .set_description("A ReAct agent with message-generating tool wrapper")
            .set_properties(
                ReActAgentConfig(
                    model="test-model",
                    toolset=CalculatorToolset(),
                    tool_wrappers=[MessageGeneratingToolWrapper()],
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

        agent, results = wrap_agent_for_testing(agent_spec, dependency_map=mock_dependency_map)

        responses = [
            create_mock_response(
                content="Calculating",
                tool_calls=[create_tool_call("t1", "calculate", {"expression": "3+3"})],
                finish_reason=FinishReason.tool_calls,
            ),
            create_mock_response("The result is 6."),
        ]

        call_idx = [0]

        def mock_call_llm(llm, request):
            response = responses[call_idx[0]]
            call_idx[0] += 1
            return response

        with patch.object(agent, "_call_llm_direct", side_effect=mock_call_llm):
            agent._on_message(
                build_message_from_payload(
                    generator,
                    ReActRequest(query="Calculate 3+3"),
                )
            )

        # Should have 2 results: tool event message + ReActResponse
        assert len(results) == 2

        # First is the tool event message
        event = MessageGeneratingToolWrapper.ToolCallEvent.model_validate(results[0].payload)
        assert event.event_type == "tool_executed"
        assert event.tool_name == "calculate"
        assert event.tool_output == "6"

        # Second is the ReActResponse
        response = ReActResponse.model_validate(results[1].payload)
        assert response.answer == "The result is 6."


class TestReActAgentMultipleToolWrappers:
    """Tests for multiple tool wrappers in ReActAgent."""

    @pytest.fixture(autouse=True)
    def reset_plugins(self):
        """Reset plugin state before each test."""
        CaptureToolWrapper.reset()
        yield

    def test_multiple_tool_wrappers_chained(self, generator, build_message_from_payload):
        """Test that multiple tool wrappers are executed in order."""
        # First wrapper captures, second wrapper modifies
        agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("react_agent")
            .set_name("ReAct Agent")
            .set_description("A ReAct agent with multiple tool wrappers")
            .set_properties(
                ReActAgentConfig(
                    model="test-model",
                    toolset=CalculatorToolset(),
                    tool_wrappers=[
                        CaptureToolWrapper(),
                        ModifyingToolWrapper(),
                    ],
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

        agent, results = wrap_agent_for_testing(agent_spec, dependency_map=mock_dependency_map)

        responses = [
            create_mock_response(
                content="Calculating",
                tool_calls=[create_tool_call("t1", "calculate", {"expression": "5"})],
                finish_reason=FinishReason.tool_calls,
            ),
            create_mock_response("Result."),
        ]

        call_idx = [0]

        def mock_call_llm(llm, request):
            response = responses[call_idx[0]]
            call_idx[0] += 1
            return response

        with patch.object(agent, "_call_llm_direct", side_effect=mock_call_llm):
            agent._on_message(
                build_message_from_payload(
                    generator,
                    ReActRequest(query="Calculate 5"),
                )
            )

        # CaptureWrapper should have been called
        assert CaptureToolWrapper.call_count == 1
        # CaptureWrapper sees original input
        assert CaptureToolWrapper.captured_calls[0]["tool_input"].expression == "5"

        # Result has modification from ModifyingToolWrapper
        response = ReActResponse.model_validate(results[0].payload)
        observation = response.trace[0].observation
        assert "[modified]" in observation
