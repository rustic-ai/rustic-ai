"""
Transformation Builder Agent for the Guild Generator.

This agent creates JSONata transformations between message types.
It understands the message format schemas and can generate both
simple payload transformations and content-based router transformations.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
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


class TransformationBuilderAgentProps(BaseAgentProps):
    """Properties for the TransformationBuilderAgent."""

    api_base_url: str = Field(
        default="http://localhost:3001",
        description="Base URL of the API server to fetch agent message formats from."
    )

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

    def __init__(self, *args, **kwargs):
        """Initialize agent and fetch message formats from API."""
        # Only initialize our custom state if not already initialized by parent
        if not hasattr(self, '_message_formats'):
            self._message_formats: Optional[Dict[str, Dict[str, Any]]] = None

        # Only fetch if we have config (means Agent.__init__ was called by framework)
        if hasattr(self, 'config'):
            self._fetch_message_formats_from_api()

    def _fetch_message_formats_from_api(self) -> None:
        """Fetch agents from API and extract message formats."""
        url = f"{self.config.api_base_url.rstrip('/')}/catalog/agents"
        try:
            logging.info(f"Fetching agent catalog from {url}")
            response = httpx.get(url, timeout=10.0)
            response.raise_for_status()
            data = response.json()
            self._message_formats = self._extract_message_formats(data)
            logging.info(f"Successfully loaded {len(self._message_formats)} message formats from API")
        except Exception as e:
            logging.error(f"Failed to fetch message formats from {url}: {e}")
            # Fall back to loading from local agent.json file if API is unavailable
            self._load_message_formats_from_file()

    def _load_message_formats_from_file(self) -> None:
        """Load message formats from local agent.json file as fallback."""
        agent_json_path = Path(__file__).parent / "agent.json"
        try:
            if agent_json_path.exists():
                logging.info(f"Loading message formats from {agent_json_path}")
                with open(agent_json_path, 'r') as f:
                    data = json.load(f)
                self._message_formats = self._extract_message_formats(data)
                logging.info(f"Successfully loaded {len(self._message_formats)} message formats from file")
            else:
                logging.warning(f"agent.json not found at {agent_json_path}, using empty message formats")
                self._message_formats = {}
        except Exception as e:
            logging.error(f"Failed to load message formats from file: {e}")
            self._message_formats = {}

    def _extract_message_formats(self, agent_data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """
        Extract unique message formats from agent data.

        Args:
            agent_data: Dictionary mapping agent class names to agent metadata

        Returns:
            Dictionary mapping message format class names to their descriptions and schemas
        """
        message_formats: Dict[str, Dict[str, Any]] = {}

        for class_name, agent_info in agent_data.items():
            handlers = agent_info.get("message_handlers", {})

            for handler_name, handler_info in handlers.items():
                # Extract input message format
                msg_format = handler_info.get("message_format")
                msg_schema = handler_info.get("message_format_schema")

                if msg_format and msg_schema and msg_format not in message_formats:
                    # Generate a description from the schema's title or use the format name
                    description = msg_schema.get("title", msg_format.split(".")[-1])

                    # Create an example from the schema (simplified)
                    example = self._generate_example_from_schema(msg_schema)

                    message_formats[msg_format] = {
                        "description": description,
                        "schema": msg_schema,
                        "example": example,
                    }

                # Extract output message formats from send_message_calls
                for send_call in handler_info.get("send_message_calls", []):
                    if isinstance(send_call, dict):
                        out_format = send_call.get("message_format")
                        out_schema = send_call.get("message_format_schema")

                        if out_format and out_schema and out_format not in message_formats:
                            description = out_schema.get("title", out_format.split(".")[-1])
                            example = self._generate_example_from_schema(out_schema)

                            message_formats[out_format] = {
                                "description": description,
                                "schema": out_schema,
                                "example": example,
                            }

        return message_formats

    def _generate_example_from_schema(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate a simple example object from a JSON schema.

        Args:
            schema: JSON schema dictionary

        Returns:
            Example object based on the schema
        """
        example = {}
        properties = schema.get("properties", {})

        for prop_name, prop_info in properties.items():
            if isinstance(prop_info, dict):
                prop_type = prop_info.get("type", "string")

                # Use default value if available
                if "default" in prop_info:
                    example[prop_name] = prop_info["default"]
                # Otherwise use type-appropriate placeholder
                elif prop_type == "string":
                    example[prop_name] = f"<{prop_name}>"
                elif prop_type == "integer" or prop_type == "number":
                    example[prop_name] = 0
                elif prop_type == "boolean":
                    example[prop_name] = False
                elif prop_type == "array":
                    example[prop_name] = []
                elif prop_type == "object":
                    example[prop_name] = {}

        return example

    def _get_message_formats(self) -> Dict[str, Dict[str, Any]]:
        """Get cached message formats. Should not be None after initialization."""
        if self._message_formats is None:
            raise RuntimeError(
                "Message formats not initialized. This should not happen after on_start."
            )
        return self._message_formats

    def _get_format_descriptions(self) -> str:
        """Generate descriptions of known message formats."""
        descriptions = []
        for format_name, info in self._get_message_formats().items():
            # Convert schema to a more readable format for the LLM
            schema_str = json.dumps(info['schema'], indent=2)
            example_str = json.dumps(info['example'], indent=2)

            desc = f"""
- {format_name}
  Description: {info['description']}
  Schema: {schema_str}
  Example: {example_str}
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
                # Preserve session_state so RouteBuilder can correlate the response
                # with the pending route request
                session_state = ctx.message.session_state or {}
                ctx.update_context(session_state)
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
