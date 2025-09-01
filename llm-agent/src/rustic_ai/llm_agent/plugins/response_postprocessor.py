from abc import ABC, abstractmethod
from typing import List, Optional

from mistralai_azure import ChatCompletionResponse
from pydantic import BaseModel, Field, model_validator

from rustic_ai.core.guild.agent import Agent, ProcessContext
from rustic_ai.core.guild.agent_ext.depends.llm.llm import LLM
from rustic_ai.core.guild.agent_ext.depends.llm.models import ChatCompletionRequest


class ResponsePostprocessor(BaseModel, ABC):
    """
    Base class for response postprocessors (plugins inherit from this).
    The implementations of this class will process the response after receiving it from the LLM.
    """

    kind: Optional[str] = Field(default=None, frozen=True, description="FQCN of the postprocessor class")

    def model_post_init(self, __context) -> None:
        if not self.kind:
            object.__setattr__(self, "kind", f"{self.__class__.__module__}.{self.__class__.__qualname__}")

    @model_validator(mode="after")
    def _enforce_kind_matches_class(self):
        fqcn = f"{self.__class__.__module__}.{self.__class__.__qualname__}"
        if self.kind and self.kind != fqcn:
            raise ValueError(f"`kind` must be {fqcn!r}, got {self.kind!r}")
        return self

    @abstractmethod
    def postprocess(
        self,
        agent: Agent,
        ctx: ProcessContext[ChatCompletionRequest],
        final_prompt: ChatCompletionRequest,
        llm_response: ChatCompletionResponse,
        llm: LLM,
    ) -> Optional[List[BaseModel]]: ...
