from abc import ABC, abstractmethod
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from rustic_ai.core.guild.agent import Agent, ProcessContext
from rustic_ai.core.guild.agent_ext.depends.llm.models import ChatCompletionRequest


class RequestPreprocessor(BaseModel, ABC):
    """
    Base class for request preprocessors (plugins inherit from this).
    The implementations of this class will process the prompts before sending them to the LLM.
    """

    kind: Optional[str] = Field(default=None, frozen=True, description="FQCN of the preprocessor class")

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
    def preprocess(
        self,
        agent: Agent,
        ctx: ProcessContext[ChatCompletionRequest],
        request: ChatCompletionRequest,
    ) -> ChatCompletionRequest: ...
