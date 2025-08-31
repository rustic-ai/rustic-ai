import pytest

from rustic_ai.core.guild.agent_ext.depends.llm.models import (
	ChatCompletionRequest,
	ChatCompletionTool,
	FunctionObject,
	ToolType,
	UserMessage,
)
from rustic_ai.llm_agent.tools.tools_provider import ToolsProvider
from rustic_ai.llm_agent.llm_agent import LLMAgent
from rustic_ai.llm_agent.llm_agent_conf import LLMAgentConfig
from rustic_ai.core.guild.builders import AgentBuilder
from rustic_ai.core.guild.dsl import AgentSpec
from rustic_ai.testing.helpers import wrap_agent_for_testing
from rustic_ai.llm_agent.plugins.llm_call_wrapper import LLMCallWrapper
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
	ChatCompletionResponse,
	ChatCompletionNamedToolChoice,
	Function,
	FunctionParameters,
)
import os


def _make_tool(name: str) -> ChatCompletionTool:
	return ChatCompletionTool(type=ToolType.function, function=FunctionObject(name=name))


def _base_request_with_no_tools() -> ChatCompletionRequest:
	return ChatCompletionRequest(messages=[UserMessage(content="hi")])


def _base_request_with_tools(tool_names: list[str]) -> ChatCompletionRequest:
	return ChatCompletionRequest(
		messages=[UserMessage(content="hi")],
		tools=[_make_tool(n) for n in tool_names],
	)


class TestToolsProvider:
	def test_preprocess_adds_tools_when_request_has_none(self):
		provider = ToolsProvider(tools=[_make_tool("search"), _make_tool("weather")])
		req = _base_request_with_no_tools()

		new_req = provider.preprocess(agent=None, ctx=None, request=req)

		# Original request is not mutated
		assert req.tools is None

		# New request has provider tools
		assert new_req.tools is not None
		assert [t.function.name for t in new_req.tools] == ["search", "weather"]

	def test_preprocess_extends_existing_tools_without_mutation(self):
		existing = _make_tool("calendar")
		provider_tool = _make_tool("email")

		provider = ToolsProvider(tools=[provider_tool])
		req = _base_request_with_tools([existing.function.name])

		# Keep a reference to the original list for mutation checks
		original_tools_list = req.tools

		new_req = provider.preprocess(agent=None, ctx=None, request=req)

		# Original request's tools list and order remain unchanged
		assert req.tools is original_tools_list
		assert [t.function.name for t in req.tools] == ["calendar"]

		# New request contains both old + provider tools in order
		assert [t.function.name for t in new_req.tools] == ["calendar", "email"]
		assert new_req.tools is not original_tools_list  # ensure a new list was created

	def test_preprocess_with_empty_provider_tools_keeps_request_tools(self):
		provider = ToolsProvider(tools=[])
		req = _base_request_with_tools(["files", "search"])

		new_req = provider.preprocess(agent=None, ctx=None, request=req)

		assert [t.function.name for t in new_req.tools] == ["files", "search"]

	def test_preprocess_handles_empty_request_tools_list(self):
		provider = ToolsProvider(tools=[_make_tool("math")])
		req = ChatCompletionRequest(messages=[UserMessage(content="hi")], tools=[])

		new_req = provider.preprocess(agent=None, ctx=None, request=req)

		assert [t.function.name for t in new_req.tools] == ["math"]


class _CapturePromptToolsWrapper(LLMCallWrapper):
	"""Test-only wrapper to capture the final prompt.tools passed to LLM."""

	captured_tools: list[str] | None = None

	def preprocess(self, agent, ctx, request: ChatCompletionRequest) -> ChatCompletionRequest:  # type: ignore[override]
		# Nothing to change, just pass through
		return request

	def postprocess(self, agent, ctx, final_prompt: ChatCompletionRequest, llm_response):  # type: ignore[override]
		# Capture the tool names in the exact order that will be sent to LLM
		tools = final_prompt.tools or []
		self.captured_tools = [t.function.name for t in tools]


class TestToolsProviderWithAgent:
	@pytest.mark.skipif(os.getenv("SKIP_EXPENSIVE_TESTS") == "true", reason="Skipping expensive tests")
	def test_tools_provider_merges_with_request_tools_and_used_by_agent(
		self, generator, build_message_from_payload, dependency_map
	):
		# Arrange: Build an agent with ToolsProvider and a capture wrapper
		capture = _CapturePromptToolsWrapper()

		agent_spec: AgentSpec = (
			AgentBuilder(LLMAgent)
			.set_id("llm_agent")
			.set_name("LLM Agent")
			.set_description("Agent that uses ToolsProvider to add tools")
			.set_properties(
				LLMAgentConfig(
					model="gpt-5-mini",
					default_system_prompt="You are a helpful assistant.",
					request_preprocessors=[
						ToolsProvider(tools=[_make_tool("search"), _make_tool("email")]),
					],
					llm_request_wrappers=[capture],
				)
			)
			.build_spec()
		)

		agent, results = wrap_agent_for_testing(agent_spec, dependency_map=dependency_map)

		# Request includes an existing tool; provider should append its tools
		request = ChatCompletionRequest(
			messages=[UserMessage(content="Say hello")],
			tools=[_make_tool("calendar")],
			max_tokens=10,
		)

		# Act
		agent._on_message(build_message_from_payload(generator, request))

		# Assert: Ensure the wrapper captured the merged tools in order
		assert capture.captured_tools == ["calendar", "search", "email"]

		# Also sanity-check the agent produced a response envelope
		assert len(results) >= 1
		assert results[0].format == get_qualified_class_name(ChatCompletionResponse)

	@pytest.mark.skipif(os.getenv("SKIP_EXPENSIVE_TESTS") == "true", reason="Skipping expensive tests")
	def test_tools_provider_used_when_request_has_no_tools(self, generator, build_message_from_payload, dependency_map):
		capture = _CapturePromptToolsWrapper()

		agent_spec: AgentSpec = (
			AgentBuilder(LLMAgent)
			.set_id("llm_agent")
			.set_name("LLM Agent")
			.set_description("Agent that supplies tools via ToolsProvider when request has none")
			.set_properties(
				LLMAgentConfig(
					model="gpt-5-mini",
					default_system_prompt="You are a helpful assistant.",
					request_preprocessors=[ToolsProvider(tools=[_make_tool("math"), _make_tool("files")])],
					llm_request_wrappers=[capture],
				)
			)
			.build_spec()
		)

		agent, results = wrap_agent_for_testing(agent_spec, dependency_map=dependency_map)

		request = ChatCompletionRequest(messages=[UserMessage(content="Say hi")])

		agent._on_message(build_message_from_payload(generator, request))

		assert capture.captured_tools == ["math", "files"]
		assert len(results) >= 1
		assert results[0].format == get_qualified_class_name(ChatCompletionResponse)

	@pytest.mark.skipif(os.getenv("SKIP_EXPENSIVE_TESTS") == "true", reason="Skipping expensive tests")
	def test_llm_returns_tool_call_for_provider_tool(self, generator, build_message_from_payload, dependency_map):
		"""
		Provide a concrete tool via ToolsProvider and force the tool call using tool_choice.
		Assert the LLM returns a tool call with the expected function name.
		"""
		# Define an "echo_text" function schema
		echo_tool = ChatCompletionTool(
			type=ToolType.function,
			function=FunctionObject(
				name="echo_text",
				parameters=FunctionParameters(
					**{
						"type": "object",
						"properties": {"text": {"type": "string"}},
						"required": ["text"],
					}
				),
				description="Echo back the provided text.",
			),
		)

		agent_spec: AgentSpec = (
			AgentBuilder(LLMAgent)
			.set_id("llm_agent")
			.set_name("LLM Agent")
			.set_description("Agent that provides echo_text tool via ToolsProvider")
			.set_properties(
				LLMAgentConfig(
					model="gpt-5-mini",
					default_system_prompt=(
						"You are a helpful assistant. When tools are relevant, prefer to call them correctly."
					),
					request_preprocessors=[ToolsProvider(tools=[echo_tool])],
				)
			)
			.build_spec()
		)

		agent, results = wrap_agent_for_testing(agent_spec, dependency_map=dependency_map)

		# Force a call to the provider tool to avoid model variance
		forced_choice = ChatCompletionNamedToolChoice(type=ToolType.function, function=Function(name="echo_text"))

		request = ChatCompletionRequest(
			messages=[
				UserMessage(
					content=(
						"Please echo back the exact phrase 'tools test success'. Use the available function if needed."
					)
				)
			],
			tool_choice=forced_choice,
		)

		agent._on_message(build_message_from_payload(generator, request))

		# Ensure we captured the tool presence and the agent yielded a result
		assert len(results) >= 1
		assert results[0].format == get_qualified_class_name(ChatCompletionResponse)

		payload = ChatCompletionResponse.model_validate(results[0].payload)
		assert len(payload.choices) > 0
		first = payload.choices[0]
		# Validate a tool call was returned for the forced tool
		assert first.message.tool_calls is not None and len(first.message.tool_calls) >= 1
		assert first.message.tool_calls[0].function.name == "echo_text"

