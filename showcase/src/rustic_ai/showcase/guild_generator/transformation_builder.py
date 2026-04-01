"""
Transformation Builder Agent for the Guild Generator.

This agent creates JSONata transformations between message types.
It understands the message format schemas and can generate both
simple payload transformations and content-based router transformations.
"""

import json
import logging
from typing import Dict, List

from pydantic import Field

from rustic_ai.core.agents.commons.message_formats import ErrorMessage
from rustic_ai.core.guild.agent import Agent, ProcessContext, processor
from rustic_ai.core.guild.dsl import BaseAgentProps
from rustic_ai.core.guild.agent_ext.depends.llm.llm import LLM
from rustic_ai.core.ui_protocol.types import TextFormat
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    SystemMessage,
    UserMessage,
)
from rustic_ai.showcase.guild_generator.models import (
    TransformRequest,
    TransformResponse,
    TransformationSpec,
)
from rustic_ai.showcase.guild_generator.utils import extract_json_from_response


# Common message format schemas
MESSAGE_FORMATS: Dict[str, Dict] = {
    "rustic_ai.core.guild.agent_ext.depends.llm.models.ChatCompletionRequest": {
        "description": "Chat completion request for LLM agents",
        "schema": {
            "messages": [{"role": "string (user/assistant/system)", "content": "string or content parts"}],
            "model": "optional string",
            "temperature": "optional float",
        },
        "example": {"messages": [{"role": "user", "content": "Hello"}]},
    },
    "rustic_ai.core.guild.agent_ext.depends.llm.models.ChatCompletionResponse": {
        "description": "Chat completion response from LLM agents",
        "schema": {
            "choices": [{"message": {"role": "string", "content": "string"}, "finish_reason": "string"}],
            "usage": {"prompt_tokens": "int", "completion_tokens": "int", "total_tokens": "int"},
        },
        "example": {"choices": [{"message": {"role": "assistant", "content": "Hello!"}, "finish_reason": "stop"}]},
    },
    "rustic_ai.core.ui_protocol.types.TextFormat": {
        "description": "Simple text format for UI display",
        "schema": {"text": "string", "title": "optional string", "description": "optional string"},
        "example": {"text": "Hello world", "title": "Greeting"},
    },
    "rustic_ai.core.ui_protocol.types.VegaLiteFormat": {
        "description": "Vega-Lite visualization format",
        "schema": {"spec": "VegaLite spec object", "title": "optional string", "alt": "optional string"},
        "example": {"spec": {"$schema": "https://vega.github.io/schema/vega-lite/v5.json", "data": {}, "mark": "bar"}},
    },
}


class TransformationBuilderAgentProps(BaseAgentProps):
    """Properties for the TransformationBuilderAgent."""

    system_prompt: str = Field(
        default="""You are a JSONata transformation expert for the Rustic AI framework. Your job is to create
JSONata expressions that transform messages between different formats.

IMPORTANT CONTEXT ABOUT TRANSFORMATION STYLES:

1. "simple" style transformations:
   - The JSONata expression operates ONLY on the message payload ($.payload fields)
   - Access fields directly: $.text, $.choices[0].message.content
   - Output format is specified separately via output_format field
   - Use for straightforward field mapping

2. "content_based_router" style transformations:
   - The JSONata expression operates on the FULL message context
   - Available context: $.payload, $.origin, $.agent_state, $.guild_state, $.topics, $.format
   - MUST return an object with at minimum: {{"format": "...", "payload": {{...}}}}
   - Can also set: topics, recipient_list, priority
   - Use when you need access to state, need to change topics/format dynamically

CRITICAL JSONata RULES:
- For "simple" style: Access payload fields directly ($.field_name)
- For "content_based_router" style: Access payload via $.payload.field_name
- Always wrap output in parentheses: ({{...}})
- Use & for string concatenation: 'prefix' & $.value & 'suffix'
- Use $append for array concatenation
- Use $map for transforming arrays
- Use $split for splitting strings
- Use $join for joining arrays

Known message formats:
{message_formats}

Respond ONLY with a JSON object in this exact format:
{{
    "transformation": {{
        "style": "simple" or "content_based_router",
        "expression_type": "jsonata",
        "handler": "<JSONata expression>",
        "output_format": "<target format class name - only for simple style>"
    }},
    "explanation": "<explanation of the transformation>"
}}"""
    )


class TransformationBuilderAgent(Agent[TransformationBuilderAgentProps]):
    """
    Agent that creates JSONata transformations between message types.

    This agent understands message format schemas and can generate
    appropriate JSONata expressions for transforming messages.
    """

    def _get_format_descriptions(self) -> str:
        """Generate descriptions of known message formats."""
        descriptions = []
        for format_name, info in MESSAGE_FORMATS.items():
            desc = f"""
- {format_name}
  Description: {info['description']}
  Schema: {json.dumps(info['schema'], indent=2)}
  Example: {json.dumps(info['example'], indent=2)}
"""
            descriptions.append(desc)
        return "\n".join(descriptions)

    @processor(TransformRequest, depends_on=["llm"])
    def build_transformation(self, ctx: ProcessContext[TransformRequest], llm: LLM):
        """
        Build a JSONata transformation based on the request.
        """
        request = ctx.payload

        system_prompt = self.config.system_prompt.format(message_formats=self._get_format_descriptions())

        user_prompt = f"""Create a JSONata transformation with these requirements:

Source format: {request.source_format}
Target format: {request.target_format}
Source agent: {request.source_agent_name}
Target agent: {request.target_agent_name}
Additional requirements: {request.requirements or 'None'}

Please generate the appropriate JSONata transformation."""

        llm_request = ChatCompletionRequest(
            messages=[
                SystemMessage(content=system_prompt),
                UserMessage(content=user_prompt),
            ]
        )

        try:
            response: ChatCompletionResponse = llm.completion(llm_request)
            response_text = response.choices[0].message.content

            try:
                # Extract JSON from potential markdown wrapper
                json_text = extract_json_from_response(response_text)
                result = json.loads(json_text)
                transform_data = result.get("transformation", {})

                transformation = TransformationSpec(
                    style=transform_data.get("style", "simple"),
                    expression_type=transform_data.get("expression_type", "jsonata"),
                    handler=transform_data.get("handler", ""),
                    output_format=transform_data.get("output_format"),
                )

                transform_response = TransformResponse(
                    transformation=transformation,
                    explanation=result.get("explanation", ""),
                )
                ctx.send(transform_response)

            except json.JSONDecodeError as e:
                logging.error(f"Failed to parse transformation response: {response_text}")
                ctx.send(
                    TextFormat(
                        text=f"**Failed to parse transformation response**\n\nThe LLM did not return valid JSON. Please try again.\n\nError: {str(e)}",
                        title="Parse Error",
                    )
                )
                ctx.send_error(
                    ErrorMessage(
                        agent_type="TransformationBuilderAgent",
                        error_type="JSONDecodeError",
                        error_message=f"Invalid JSON response: {str(e)}",
                    )
                )

        except Exception as e:
            logging.error(f"Error building transformation: {e}")
            ctx.send(
                TextFormat(
                    text=f"**Transformation Creation Failed**\n\nAn error occurred while creating the transformation.\n\nError: {str(e)}",
                    title="Error",
                )
            )
            ctx.send_error(
                ErrorMessage(
                    agent_type="TransformationBuilderAgent",
                    error_type=type(e).__name__,
                    error_message=str(e),
                )
            )
