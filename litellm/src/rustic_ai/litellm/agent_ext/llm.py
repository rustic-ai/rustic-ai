from typing import List, Optional

import litellm

from rustic_ai.core.guild.agent_ext.depends.dependency_resolver import (
    DependencyResolver,
)
from rustic_ai.core.guild.agent_ext.depends.llm import LLM
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionTool,
)
from rustic_ai.litellm.conf import LiteLLMConf
from rustic_ai.litellm.utils import ResponseUtils


class LiteLLM(LLM):
    def __init__(self, props: LiteLLMConf):
        litellm.drop_params = True
        litellm.set_verbose = False
        # set callbacks
        litellm.input_callback = []
        litellm.success_callback = []
        litellm.failure_callback = []
        self.pre_messages = props.messages
        self._model = props.model
        self.client_props = props.model_dump(
            mode="json",
            exclude_unset=True,
            exclude_none=True,
            exclude={
                "message_memory",
                "toolset",
                "filter_attachments",
                "extract_tool_calls",
                "skip_chat_response_on_tool_call",
                "retries_on_tool_parse_error",
            },
        )

        self.tool_manager = props.get_tools_manager()

    def _prep_prompt(self, prompt: ChatCompletionRequest) -> dict:
        messages = self.pre_messages if self.pre_messages else []

        all_messages = messages + prompt.messages

        messages_dict = [m.model_dump(exclude_none=True) for m in all_messages]

        tools: List[ChatCompletionTool] = self.tool_manager.tools if self.tool_manager else []
        if prompt.tools:
            tools.extend(prompt.tools)

        prompt_dict = prompt.model_dump(exclude_none=True, exclude_unset=True)

        full_prompt = {
            **self.client_props,
            **prompt_dict,
            "messages": messages_dict,
        }

        if tools:
            # Convert ChatCompletionTool objects to dictionaries for litellm
            full_prompt["tools"] = [tool.model_dump(exclude_none=True) for tool in tools]

        return full_prompt

    def completion(self, prompt: ChatCompletionRequest, model: Optional[str] = None):
        full_prompt = self._prep_prompt(prompt)

        if model:
            full_prompt["model"] = model

        completion = litellm.completion(**full_prompt)
        response: ChatCompletionResponse = ResponseUtils.from_litellm(completion)
        response.input_messages = full_prompt["messages"]  # Store input messages in the response
        return response

    async def async_completion(self, prompt: ChatCompletionRequest, model: Optional[str] = None):
        full_prompt = self._prep_prompt(prompt)

        if model:
            full_prompt["model"] = model

        completion = await litellm.acompletion(**full_prompt)
        response: ChatCompletionResponse = ResponseUtils.from_litellm(completion)
        response.input_messages = full_prompt["messages"]  # Store input messages in the response
        return response

    @property
    def model(self) -> str:
        return self._model

    def get_config(self) -> dict:
        return self.client_props


class LiteLLMResolver(DependencyResolver[LLM]):
    memoize_resolution: bool = False

    def __init__(self, model: str, conf: dict = {}):
        super().__init__()
        conf["model"] = model
        self.props = LiteLLMConf.model_validate(conf)
        self.LiteLLM = LiteLLM(self.props)

    def resolve(self, guild_id: str, agent_id: str) -> LLM:
        return self.LiteLLM  # We can always return the same instance of LiteLLM
