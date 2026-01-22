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
from rustic_ai.llm_agent.plugins.response_postprocessor import ResponsePostprocessor


class StructuredOutputPlugin(ResponsePostprocessor):
    def postprocess(self, agent: Agent, ctx: ProcessContext[ChatCompletionRequest], final_prompt: ChatCompletionRequest,
                    llm_response: ChatCompletionResponse, llm: LLM) -> Optional[List[BaseModel]]:
        output_format = ctx.payload.response_format
        if isinstance(output_format, str):
            format_type = get_class_from_name(output_format)
            # If it's a Pydantic model class, convert to JSON schema
            if isinstance(format_type, type) and issubclass(format_type, BaseModel):
                result = []
                for choice in llm_response.choices:
                    content = json.loads(choice.message.content)
                    result.append(format_type.model_validate(content))
                return result
            else:
                raise ValueError(f"Unsupported response format: {output_format}")
        else:
            raise ValueError(f"Invalid response format type: {type(output_format)}")
