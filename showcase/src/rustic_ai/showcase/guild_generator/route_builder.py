"""
Route Builder Agent for the Guild Generator.

This agent creates RoutingRule specifications from agent and transformation
information, and manages the routes stored in guild state.
"""

import json
import logging
from typing import Any, Dict, Optional

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
    ActionType,
    OrchestratorAction,
    RouteRequest,
    RouteResponse,
    TransformationSpec,
)
from rustic_ai.showcase.guild_generator.utils import extract_json_from_response


class RouteBuilderAgentProps(BaseAgentProps):
    """Properties for the RouteBuilderAgent."""

    system_prompt: str = Field(
        default="""You are a routing expert for the Rustic AI framework. Your job is to create
RoutingRule specifications that define how messages flow between agents.

A RoutingRule has these fields:
- agent: {{"id": "agent_id", "name": "agent_name"}} - identifies the source agent (either id or name)
- agent_type: "full.class.name" - alternative to agent, matches all agents of this type
- method_name: "method_name" - optional, specific method that sends the message
- message_format: "full.format.class.name" - the message format this rule applies to (MUST be a valid format from the agent's output_formats)
- destination: {{"topics": "topic_name" or ["topics"], "recipient_list": [], "priority": null}}
- route_times: -1 for always, or a specific number of times
- transformer: optional transformation to apply (see below)
- process_status: "completed" if this ends the message processing chain
- guild_state_update: optional update to guild state

IMPORTANT: The message_format field MUST be a fully qualified class name of the actual message type
that the source agent sends. Use the output_formats from the agent info provided below.
Do NOT make up message format names - only use formats that are listed in the agent's output_formats.

## Common Routing Patterns:

**Pattern 1: UserProxyAgent → Agent** (User input to agent)
- Source: agent_type = "rustic_ai.core.agents.utils.user_proxy_agent.UserProxyAgent"
- Message format: "rustic_ai.core.guild.agent_ext.depends.llm.models.ChatCompletionRequest"
- Destination topics: Look up the target agent's additional_topics or use "default_topic"
- May need transformer to match target agent's input format

**Pattern 2: Agent → user_message_broadcast** (Agent output to user)
- Source: agent = {{"name": "AgentName"}}
- Message format: Use agent's output_format (often TextFormat, ChatCompletionResponse, etc.)
- Destination topics: "user_message_broadcast"
- Set process_status: "completed" to end the processing chain
- May need transformer to convert to MarkdownFormat for user display

**Pattern 3: Agent A → Agent B** (Inter-agent communication)
- Source: agent = {{"name": "SourceAgent"}}
- Message format: Use source agent's output_format
- Destination topics: Target agent's topic (from additional_topics or "default_topic")
- May need transformer if formats don't match

Transformer format for "simple" style:
{{
    "style": "simple",
    "output_format": "target.format.class",
    "expression_type": "jsonata",
    "expression": "JSONata expression on $.payload"
}}

Transformer format for "content_based_router" style (for conditional routing):
{{
    "style": "content_based_router",
    "expression_type": "jsonata",
    "handler": "JSONata expression returning {{\"topics\": \"destination_topic\", \"format\": \"output.format.class\", \"payload\": {{...}}}}"
}}

Example transformer for routing to user_message_broadcast:
{{
    "style": "content_based_router",
    "expression_type": "jsonata",
    "handler": "({{\"topics\": \"user_message_broadcast\", \"format\": \"MarkdownFormat\", \"payload\": {{\"text\": $.payload.text ? $.payload.text : $.payload.content}}}})"
}}

Respond ONLY with a JSON object in this exact format:
{{
    "routing_rule": {{<complete RoutingRule>}},
    "explanation": "<explanation of the routing rule>"
}}"""
    )


class RouteBuilderAgent(Agent[RouteBuilderAgentProps]):
    """
    Agent that creates RoutingRule specifications.

    This agent takes routing requests and creates complete RoutingRule
    objects that can be added to a guild's routing slip.
    """

    def _get_agent_message_info(self) -> str:
        """Get formatted agent message info from guild state for the LLM prompt."""
        guild_state = self.get_guild_state() or {}
        guild_builder = guild_state.get("guild_builder", {})

        agent_info_list = guild_builder.get("agent_message_info", [])

        if not agent_info_list:
            return "No agents have been added yet."

        info_lines = ["Available agents and their message types:"]
        for agent_info in agent_info_list:
            name = agent_info.get("agent_name", "Unknown")
            agent_id = agent_info.get("agent_id", "unknown")
            class_name = agent_info.get("class_name", "")
            input_fmts = agent_info.get("input_formats", [])
            output_fmts = agent_info.get("output_formats", [])

            info_lines.append(f"\n- Agent: {name} (id: {agent_id})")
            info_lines.append(f"  Class: {class_name}")
            info_lines.append(f"  Input formats (accepts): {', '.join(input_fmts) if input_fmts else 'any'}")
            info_lines.append(f"  Output formats (sends): {', '.join(output_fmts) if output_fmts else 'varies'}")

        # Also include the system UserProxyAgent
        info_lines.append("\n- Agent: UserProxyAgent (id: user_proxy)")
        info_lines.append("  Class: rustic_ai.core.agents.utils.user_proxy_agent.UserProxyAgent")
        info_lines.append("  Input formats (accepts): rustic_ai.core.guild.agent_ext.depends.llm.models.ChatCompletionRequest")
        info_lines.append("  Output formats (sends): rustic_ai.core.guild.agent_ext.depends.llm.models.ChatCompletionRequest")

        # Include common destination topics
        info_lines.append("\n\nCommon destination topics:")
        info_lines.append("- user_message_broadcast: Send messages to the user interface")
        info_lines.append("- default_topic: Send to agents listening on the default topic")

        return "\n".join(info_lines)

    @processor(
        OrchestratorAction,
        predicate=lambda self, msg: msg.payload.get("action") == ActionType.ADD_ROUTE,
        depends_on=["llm"],
    )
    def handle_add_route_action(self, ctx: ProcessContext[OrchestratorAction], llm: LLM):
        """
        Handle add_route action from the orchestrator.
        """
        action = ctx.payload
        details = action.details

        source_agent = details.get("source_agent", "")
        target_agent = details.get("target_agent", "")
        source_format = details.get("source_format", "")
        target_format = details.get("target_format", "")
        transformation_requirements = details.get("transformation", "")

        # Get agent message info from guild state
        agent_info = self._get_agent_message_info()

        user_prompt = f"""Create a routing rule with these requirements:

Source agent: {source_agent}
Target agent/topic: {target_agent}
Source message format: {source_format or 'Not specified - look up from agent info below'}
Target message format: {target_format or 'Not specified - look up from agent info below'}
Transformation requirements: {transformation_requirements or 'None'}
Original user request: {action.user_message}

{agent_info}

IMPORTANT: Use the exact message format class names from the agent's output_formats above.
For example, if routing from an LLMAgent, use "rustic_ai.core.guild.agent_ext.depends.llm.models.ChatCompletionResponse".

Please generate a complete RoutingRule specification."""

        self._build_route(ctx, llm, user_prompt)

    @processor(RouteRequest, depends_on=["llm"])
    def handle_route_request(self, ctx: ProcessContext[RouteRequest], llm: LLM):
        """
        Handle direct route requests.
        """
        request = ctx.payload

        transformer_desc = ""
        if request.transformation:
            transformer_desc = f"""
Transformation to apply:
- Style: {request.transformation.style}
- Handler/Expression: {request.transformation.handler}
- Output format: {request.transformation.output_format or 'N/A'}
"""

        # Get agent message info from guild state
        agent_info = self._get_agent_message_info()

        user_prompt = f"""Create a routing rule with these requirements:

Agent name: {request.agent_name}
Agent ID: {request.agent_id or 'Not specified'}
Agent type: {request.agent_type or 'Not specified'}
Method name: {request.method_name or 'Not specified'}
Message format: {request.message_format}
Destination topic: {request.destination_topic or 'Not specified'}
Route times: {request.route_times}
{transformer_desc}

{agent_info}

IMPORTANT: Use the exact message format class names from the agent's output_formats above.

Please generate a complete RoutingRule specification."""

        self._build_route(ctx, llm, user_prompt)

    def _build_route(self, ctx: ProcessContext, llm: LLM, user_prompt: str):
        """
        Build a routing rule using the LLM.
        """
        llm_request = ChatCompletionRequest(
            messages=[
                SystemMessage(content=self.config.system_prompt),
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
                route_response = RouteResponse(
                    routing_rule=result.get("routing_rule", {}),
                    explanation=result.get("explanation", ""),
                )
                ctx.send(route_response)

            except json.JSONDecodeError as e:
                logging.error(f"Failed to parse route response: {response_text}")
                ctx.send(
                    TextFormat(
                        text=f"**Failed to parse route response**\n\nThe LLM did not return valid JSON. Please try again.\n\nError: {str(e)}",
                        title="Parse Error",
                    )
                )
                ctx.send_error(
                    ErrorMessage(
                        agent_type="RouteBuilderAgent",
                        error_type="JSONDecodeError",
                        error_message=f"Invalid JSON response: {str(e)}",
                    )
                )

        except Exception as e:
            logging.error(f"Error building route: {e}")
            ctx.send(
                TextFormat(
                    text=f"**Route Creation Failed**\n\nAn error occurred while creating the route.\n\nError: {str(e)}",
                    title="Error",
                )
            )
            ctx.send_error(
                ErrorMessage(
                    agent_type="RouteBuilderAgent",
                    error_type=type(e).__name__,
                    error_message=str(e),
                )
            )
