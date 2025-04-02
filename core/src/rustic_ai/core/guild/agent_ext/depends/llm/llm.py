from abc import ABC, abstractmethod

from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
)


class LLM(ABC):

    @abstractmethod
    def completion(self, prompt: ChatCompletionRequest) -> ChatCompletionResponse:
        pass

    @abstractmethod
    async def async_completion(self, prompt: ChatCompletionRequest) -> ChatCompletionResponse:
        pass

    @property
    @abstractmethod
    def model(self) -> str:
        pass

    @abstractmethod
    def get_config(self) -> dict:
        pass
