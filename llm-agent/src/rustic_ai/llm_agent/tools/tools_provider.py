from rustic_ai.core.guild.agent import Agent, ProcessContext
from rustic_ai.core.guild.agent_ext.depends.llm.llm import LLM
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ChatCompletionRequest,
    ChatCompletionTool,
)
from rustic_ai.llm_agent.plugins.request_preprocessor import RequestPreprocessor


class ToolsProvider(RequestPreprocessor):
    """
    A request preprocessor that adds a list of tools to the request.
    If the request already has tools, the provider's tools are appended to the existing list.
    If the request has no tools, the provider's tools become the request's tools.
    If the LLM makes a tool call, it will be returned in the ChatCompletetionResponse.
    """

    tools: list[ChatCompletionTool]

    def preprocess(
        self,
        agent: Agent,
        ctx: ProcessContext[ChatCompletionRequest],
        request: ChatCompletionRequest,
        llm: LLM,
    ) -> ChatCompletionRequest:

        _tools = list(request.tools or [])
        _tools.extend(self.tools)

        return request.model_copy(update={"tools": _tools})
