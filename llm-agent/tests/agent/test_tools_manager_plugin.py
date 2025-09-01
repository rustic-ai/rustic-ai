import json
import os
from typing import List, Optional, Type

from pydantic import BaseModel
import pytest

from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ChatCompletionNamedToolChoice,
    ChatCompletionRequest,
    ChatCompletionResponse,
    Function,
    ToolType,
    UserMessage,
)
from rustic_ai.core.guild.agent_ext.depends.llm.tools_manager import ToolSpec
from rustic_ai.core.guild.builders import AgentBuilder
from rustic_ai.core.guild.dsl import AgentSpec
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.llm_agent.llm_agent import LLMAgent
from rustic_ai.llm_agent.llm_agent_conf import LLMAgentConfig
from rustic_ai.llm_agent.plugins.llm_call_wrapper import LLMCallWrapper
from rustic_ai.llm_agent.tools.tools_manager_plugin import (
    ToolsManagerPlugin,
    ToolspecsListProvider,
)

from rustic_ai.testing.helpers import wrap_agent_for_testing


def _make_tool(name: str, parameter_class: Type[BaseModel]) -> ToolSpec:
    return ToolSpec(
        name=name,
        description=f"Tool for {name}",
        parameter_class=parameter_class,
    )


def _base_request_with_no_tools() -> ChatCompletionRequest:
    return ChatCompletionRequest(messages=[UserMessage(content="hi")])


def _base_request_with_tools(toolspecs: list[ToolSpec]) -> ChatCompletionRequest:
    tools = {tool.name: tool.chat_tool for tool in toolspecs}
    return ChatCompletionRequest(
        messages=[UserMessage(content="hi")],
        tools=list(tools.values()),
    )


class SearchParameters(BaseModel):
    query: str


class WeatherParameters(BaseModel):
    location: str


class CalendarParameters(BaseModel):
    date: str
    time: str


class EmailParameters(BaseModel):
    recipient: str
    subject: str
    body: str


class MathParameters(BaseModel):
    expression: str


class FileParameters(BaseModel):
    filename: str
    operation: str  # e.g., "read", "write"


class EchoParameters(BaseModel):
    text: str


class TestToolsManagerPlugin:
    def test_preprocess_adds_tools_when_request_has_none(self):
        provider = ToolsManagerPlugin(
            toolset=ToolspecsListProvider(
                tools=[
                    _make_tool("search", SearchParameters),
                    _make_tool("weather", WeatherParameters),
                ]
            )
        )
        req = _base_request_with_no_tools()
        new_req = provider.preprocess(agent=None, ctx=None, request=req)
        assert new_req.tools is not None
        assert [t.function.name for t in new_req.tools] == ["search", "weather"]

    def test_preprocess_extends_existing_tools_without_mutation(self):
        existing = _make_tool("calendar", CalendarParameters)
        provider_tool = _make_tool("email", EmailParameters)
        provider = ToolsManagerPlugin(
            toolset=ToolspecsListProvider(
                tools=[
                    provider_tool,
                ]
            )
        )
        req = _base_request_with_tools([existing])
        original_tools_list = req.tools
        new_req = provider.preprocess(agent=None, ctx=None, request=req)
        assert req.tools is original_tools_list
        assert [t.function.name for t in req.tools] == ["calendar"]
        assert [t.function.name for t in new_req.tools] == ["calendar", "email"]
        assert new_req.tools is not original_tools_list

    def test_preprocess_handles_empty_request_tools_list(self):
        provider = ToolsManagerPlugin(
            toolset=ToolspecsListProvider(
                tools=[
                    _make_tool("math", MathParameters),
                ]
            )
        )
        req = ChatCompletionRequest(messages=[UserMessage(content="hi")], tools=[])
        new_req = provider.preprocess(agent=None, ctx=None, request=req)
        assert [t.function.name for t in new_req.tools] == ["math"]


class _CapturePromptToolsWrapper(LLMCallWrapper):
    captured_tools: list[str] | None = None

    def preprocess(self, agent, ctx, request: ChatCompletionRequest) -> ChatCompletionRequest:
        return request

    def postprocess(self, agent, ctx, final_prompt: ChatCompletionRequest, llm_response) -> Optional[List[BaseModel]]:
        tools = final_prompt.tools or []
        self.captured_tools = [t.function.name for t in tools]
        return tools


class TestToolsManagerPluginWithAgent:
    @pytest.mark.skipif(os.getenv("SKIP_EXPENSIVE_TESTS") == "true", reason="Skipping expensive tests")
    def test_tools_manager_plugin_merges_with_request_tools_and_used_by_agent(
        self, generator, build_message_from_payload, dependency_map
    ):
        capture = _CapturePromptToolsWrapper()
        agent_spec: AgentSpec = (
            AgentBuilder(LLMAgent)
            .set_id("llm_agent")
            .set_name("LLM Agent")
            .set_description("Agent that uses ToolsManagerPlugin to add tools")
            .set_properties(
                LLMAgentConfig(
                    model="gpt-5-mini",
                    default_system_prompt="You are a helpful assistant.",
                    llm_request_wrappers=[
                        capture,
                        ToolsManagerPlugin(
                            toolset=ToolspecsListProvider(
                                tools=[
                                    _make_tool("search", SearchParameters),
                                    _make_tool("email", EmailParameters),
                                ]
                            )
                        ),
                    ],
                )
            )
            .build_spec()
        )
        agent, results = wrap_agent_for_testing(agent_spec, dependency_map=dependency_map)
        request = ChatCompletionRequest(
            messages=[UserMessage(content="Say hello")],
            tools=[_make_tool("calendar", CalendarParameters).chat_tool],
            max_tokens=10,
        )
        agent._on_message(build_message_from_payload(generator, request))
        assert capture.captured_tools == ["calendar", "search", "email"]
        assert len(results) >= 2

        results_by_format = {r.format: r for r in results}
        assert get_qualified_class_name(ChatCompletionResponse) in results_by_format

    @pytest.mark.skipif(os.getenv("SKIP_EXPENSIVE_TESTS") == "true", reason="Skipping expensive tests")
    def test_tools_manager_plugin_used_when_request_has_no_tools(
        self, generator, build_message_from_payload, dependency_map
    ):
        capture = _CapturePromptToolsWrapper()
        agent_spec: AgentSpec = (
            AgentBuilder(LLMAgent)
            .set_id("llm_agent")
            .set_name("LLM Agent")
            .set_description("Agent that supplies tools via ToolsManagerPlugin when request has none")
            .set_properties(
                LLMAgentConfig(
                    model="gpt-5-mini",
                    default_system_prompt="You are a helpful assistant.",
                    llm_request_wrappers=[
                        capture,
                        ToolsManagerPlugin(
                            toolset=ToolspecsListProvider(
                                tools=[
                                    _make_tool("math", MathParameters),
                                    _make_tool("files", FileParameters),
                                ]
                            )
                        ),
                    ],
                )
            )
            .build_spec()
        )
        agent, results = wrap_agent_for_testing(agent_spec, dependency_map=dependency_map)
        request = ChatCompletionRequest(messages=[UserMessage(content="Say hi")])
        agent._on_message(build_message_from_payload(generator, request))
        assert capture.captured_tools == ["math", "files"]

        assert len(results) >= 2
        results_by_format = {r.format: r for r in results}
        assert get_qualified_class_name(ChatCompletionResponse) in results_by_format

    @pytest.mark.skipif(os.getenv("SKIP_EXPENSIVE_TESTS") == "true", reason="Skipping expensive tests")
    def test_llm_returns_tool_call_for_manager_plugin_tool(self, generator, build_message_from_payload, dependency_map):
        agent_spec: AgentSpec = (
            AgentBuilder(LLMAgent)
            .set_id("llm_agent")
            .set_name("LLM Agent")
            .set_description("Agent that provides echo_text tool via ToolsManagerPlugin")
            .set_properties(
                LLMAgentConfig(
                    model="gpt-5-mini",
                    default_system_prompt=(
                        "You are a helpful assistant. When tools are relevant, prefer to call them correctly."
                    ),
                    llm_request_wrappers=[
                        ToolsManagerPlugin(
                            toolset=ToolspecsListProvider(
                                tools=[
                                    _make_tool("echo_text", EchoParameters),
                                ]
                            )
                        )
                    ],
                )
            )
            .build_spec()
        )
        agent, results = wrap_agent_for_testing(agent_spec, dependency_map=dependency_map)
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
        assert len(results) >= 2

        results_by_format = {r.format: r for r in results}
        assert get_qualified_class_name(ChatCompletionResponse) in results_by_format
        response = results_by_format[get_qualified_class_name(ChatCompletionResponse)]
        payload = ChatCompletionResponse.model_validate(response.payload)
        assert len(payload.choices) > 0
        first = payload.choices[0]
        assert first.message.tool_calls is not None and len(first.message.tool_calls) >= 1
        assert first.message.tool_calls[0].function.name == "echo_text"
        assert first.message.tool_calls[0].function.arguments is not None
        arg_text = json.loads(first.message.tool_calls[0].function.arguments)["text"]

        assert get_qualified_class_name(EchoParameters) in results_by_format
        tool_params = results_by_format[get_qualified_class_name(EchoParameters)]
        params = EchoParameters.model_validate(tool_params.payload)
        assert params.text == arg_text
