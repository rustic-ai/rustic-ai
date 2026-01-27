import json
from typing import List, Optional

from pydantic import BaseModel

from rustic_ai.core import Agent
from rustic_ai.core.guild.agent import ProcessContext
from rustic_ai.core.guild.agent_ext.depends.llm import LLM
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
)
from rustic_ai.core.utils.basic_class_utils import get_class_from_name
from rustic_ai.llm_agent import LLMCallWrapper


class StructuredOutputPlugin(LLMCallWrapper):
    output_format_class_name: str

    def preprocess(self, agent: Agent, ctx: ProcessContext[ChatCompletionRequest], request: ChatCompletionRequest,
                   llm: LLM) -> ChatCompletionRequest:
        return request.model_copy(update={"response_format": self.output_format_class_name})

    def postprocess(self, agent: Agent, ctx: ProcessContext[ChatCompletionRequest], final_prompt: ChatCompletionRequest,
                    llm_response: ChatCompletionResponse, llm: LLM) -> Optional[List[BaseModel]]:
        format_type = get_class_from_name(self.output_format_class_name)
        # If it's a Pydantic model class, convert to JSON schema
        if isinstance(format_type, type) and issubclass(format_type, BaseModel):
            result = []
            for choice in llm_response.choices:
                content = json.loads(choice.message.content)
                result.append(format_type.model_validate(content))
            return result
        else:
            raise ValueError(f"Unsupported response format: {self.output_format_class_name}")
