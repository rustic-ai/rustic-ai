from typing import List

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


class LiteLLM(LLM):
    def __init__(self, props: LiteLLMConf):
        self.preset_messages = props.messages
        self.preset_tools = props.tools
        self._model = props.model
        self.client_props = props.model_dump(mode="json", exclude_unset=True, exclude_none=True)

    def _prep_prompt(self, prompt: ChatCompletionRequest) -> dict:
        messages = self.preset_messages if self.preset_messages else []

        all_messages = messages + prompt.messages

        messages_dict = [m.model_dump(exclude_none=True) for m in all_messages]

        tools: List[ChatCompletionTool] = self.preset_tools if self.preset_tools else []
        if prompt.tools:
            tools.extend(prompt.tools)

        full_prompt = {
            **self.client_props,
            **prompt.model_dump(exclude_unset=True, exclude_none=True),
            "messages": messages_dict,
        }

        if tools:
            full_prompt["tools"] = tools

        return full_prompt

    def completion(self, prompt: ChatCompletionRequest):
        full_prompt = self._prep_prompt(prompt)

        completion = litellm.completion(**full_prompt)
        response = ChatCompletionResponse.from_litellm_completion(completion)
        return response

    async def async_completion(self, prompt: ChatCompletionRequest):
        full_prompt = self._prep_prompt(prompt)

        completion = await litellm.acompletion(**full_prompt)
        response = ChatCompletionResponse.from_litellm_completion(completion)
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
