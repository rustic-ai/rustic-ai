"""
Route Builder Agent for the Guild Generator.

This agent creates RoutingRule specifications from agent and transformation
information, and manages the routes stored in guild state.

It delegates transformation creation to the TransformationBuilder agent
when message formats differ between source and target agents.
"""

import json
import logging
import uuid
from typing import Any, Dict, List, Optional, Tuple

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
    TransformRequest,
    TransformResponse,
)
from rustic_ai.showcase.guild_generator.utils import extract_json_from_response


class RouteBuilderAgentProps(BaseAgentProps):
    """Properties for the RouteBuilderAgent."""

    system_prompt: str = Field(
        default="""You are a routing expert for the Rustic AI framework. Your job is to create
RoutingRule specifications that define how messages flow between agents.

NOTE: This agent focuses ONLY on routing logic. Message transformations are handled by the
TransformationBuilder agent - do NOT include transformer fields in your response.

A RoutingRule has these fields:
- agent: {{"id": "agent_id", "name": "agent_name"}} - identifies the source agent (either id or name)
- agent_type: "full.class.name" - alternative to agent, matches all agents of this type
- method_name: "method_name" - optional, specific method that sends the message
- message_format: "full.format.class.name" - the message format this rule applies to (MUST be a valid format from the agent's output_formats)
- destination: {{"topics": "topic_name" or ["topics"], "recipient_list": [], "priority": null}}
- route_times: -1 for always, or a specific number of times
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

**Pattern 2: Agent → user_message_broadcast** (Agent output to user)
- Source: agent = {{"name": "AgentName"}}
- Message format: Use agent's output_format (often TextFormat, ChatCompletionResponse, etc.)
- Destination topics: "user_message_broadcast"
- Set process_status: "completed" to end the processing chain

**Pattern 3: Agent A → Agent B** (Inter-agent communication)
- Source: agent = {{"name": "SourceAgent"}}
- Message format: Use source agent's output_format
- Destination topics: Target agent's topic (from additional_topics or "default_topic")

DO NOT INCLUDE TRANSFORMER FIELDS. Transformations will be added automatically when needed.

Respond ONLY with a JSON object in this exact format:
{{
    "routing_rule": {{<complete RoutingRule WITHOUT transformer field>}},
    "explanation": "<explanation of the routing rule>",
    "source_format": "<the message format the source agent sends>",
    "target_format": "<the message format the target agent expects>"
}}"""
    )


class RouteBuilderAgent(Agent[RouteBuilderAgentProps]):
    """
    Agent that creates RoutingRule specifications.

    This agent delegates transformation creation to TransformationBuilder when
    message formats differ between source and target agents. It focuses on
    routing logic and uses async message passing to coordinate with other agents.
    """

    def __init__(self, *args, **kwargs):
        """Initialize agent with empty pending routes tracking."""
        # Only initialize our custom state if not already initialized
        if not hasattr(self, '_pending_routes'):
            # Track pending route requests waiting for transformations
            # Key: correlation_id, Value: dict with route context
            self._pending_routes: Dict[str, Dict[str, Any]] = {}

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

    def _get_agent_formats(self, agent_name: str) -> Tuple[List[str], List[str]]:
        """
        Look up agent's input and output formats from guild state.

        Args:
            agent_name: Name of the agent to look up

        Returns:
            Tuple of (input_formats, output_formats)
        """
        guild_state = self.get_guild_state() or {}
        agent_info_list = guild_state.get("guild_builder", {}).get("agent_message_info", [])

        # Check guild agents
        for agent_info in agent_info_list:
            if agent_info.get("agent_name") == agent_name or agent_info.get("agent_id") == agent_name:
                return (
                    agent_info.get("input_formats", []),
                    agent_info.get("output_formats", [])
                )

        # Check for UserProxyAgent
        if "userproxy" in agent_name.lower():
            chat_completion = "rustic_ai.core.guild.agent_ext.depends.llm.models.ChatCompletionRequest"
            return ([chat_completion], [chat_completion])

        logging.warning(f"No format info found for agent: {agent_name}")
        return ([], [])

    def _needs_transformation(self, source_format: str, target_format: str) -> bool:
        """
        Determine if a transformation is needed between two formats.

        Args:
            source_format: Message format from source agent
            target_format: Message format expected by target agent

        Returns:
            True if transformation is needed, False otherwise
        """
        # Same format = no transformation needed
        if source_format == target_format:
            return False

        # Generic/any formats don't need transformation
        if source_format in ["any", "generic_json", "configurable"]:
            return False
        if target_format in ["any", "generic_json", "configurable"]:
            return False

        # Empty formats
        if not source_format or not target_format:
            return False

        # Different formats = transformation needed
        return True

    def _select_best_format_pair(
        self,
        source_formats: List[str],
        target_formats: List[str]
    ) -> Tuple[Optional[str], Optional[str], bool]:
        """
        Select the best source and target format pair from available formats.

        Args:
            source_formats: List of formats the source agent can send
            target_formats: List of formats the target agent can accept

        Returns:
            Tuple of (source_format, target_format, needs_transformation)
        """
        if not source_formats or not target_formats:
            return (None, None, False)

        # First, try to find exact match
        for src_fmt in source_formats:
            if src_fmt in target_formats:
                return (src_fmt, src_fmt, False)

        # No exact match - select first available from each
        # Prefer non-generic formats
        source_format = None
        for fmt in source_formats:
            if fmt not in ["any", "generic_json", "configurable"]:
                source_format = fmt
                break
        if not source_format:
            source_format = source_formats[0]

        target_format = None
        for fmt in target_formats:
            if fmt not in ["any", "generic_json", "configurable"]:
                target_format = fmt
                break
        if not target_format:
            target_format = target_formats[0]

        return (source_format, target_format, True)

    @processor(
        OrchestratorAction,
        predicate=lambda self, msg: msg.payload.get("action") == ActionType.ADD_ROUTE,
        depends_on=["llm"],
    )
    def handle_add_route_action(self, ctx: ProcessContext[OrchestratorAction], llm: LLM):
        """
        Handle add_route action from the orchestrator.

        This method determines if transformation is needed and delegates to
        TransformationBuilder if formats differ.
        """
        action = ctx.payload
        details = action.details

        source_agent = details.get("source_agent", "")
        target_agent = details.get("target_agent", "")
        transformation_requirements = details.get("transformation_requirements", "")

        # Get agent message info from guild state
        agent_info = self._get_agent_message_info()

        user_prompt = f"""Create a routing rule with these requirements:

Source agent: {source_agent}
Target agent/topic: {target_agent}
Transformation requirements: {transformation_requirements or 'None'}
Original user request: {action.user_message}

{agent_info}

IMPORTANT:
- Use the exact message format class names from the agent's output_formats above.
- Include both source_format and target_format in your response so we can determine if transformation is needed.
- DO NOT include transformer field - transformations are handled separately.

Please generate a complete RoutingRule specification."""

        # Build route with async transformation support
        self._build_route_async(
            ctx=ctx,
            llm=llm,
            user_prompt=user_prompt,
            source_agent_name=source_agent,
            target_agent_name=target_agent,
            transformation_requirements=transformation_requirements
        )

    @processor(RouteRequest, depends_on=["llm"])
    def handle_route_request(self, ctx: ProcessContext[RouteRequest], llm: LLM):
        """
        Handle direct route requests.

        If transformation is provided in the request, use it directly.
        Otherwise, check if transformation is needed and delegate to TransformationBuilder.
        """
        request = ctx.payload

        # If transformation already provided, use traditional flow
        if request.transformation:
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

{agent_info}

IMPORTANT: Use the exact message format class names from the agent's output_formats above.

Please generate a complete RoutingRule specification."""

            self._build_route_with_transformation(
                ctx=ctx,
                llm=llm,
                user_prompt=user_prompt,
                transformation=request.transformation
            )
        else:
            # Use async transformation flow
            agent_info = self._get_agent_message_info()

            user_prompt = f"""Create a routing rule with these requirements:

Agent name: {request.agent_name}
Agent ID: {request.agent_id or 'Not specified'}
Agent type: {request.agent_type or 'Not specified'}
Method name: {request.method_name or 'Not specified'}
Message format: {request.message_format}
Destination topic: {request.destination_topic or 'Not specified'}
Route times: {request.route_times}

{agent_info}

IMPORTANT:
- Use the exact message format class names from the agent's output_formats above.
- Include both source_format and target_format in your response.
- DO NOT include transformer field.

Please generate a complete RoutingRule specification."""

            self._build_route_async(
                ctx=ctx,
                llm=llm,
                user_prompt=user_prompt,
                source_agent_name=request.agent_name,
                target_agent_name=request.destination_topic or "unknown",
                transformation_requirements=""
            )

    @processor(TransformResponse)
    def handle_transformation_response(self, ctx: ProcessContext[TransformResponse]):
        """
        Handle transformation response from TransformationBuilder.

        Retrieves the pending route request, adds the transformation, and completes the route.
        """
        transform_response = ctx.payload
        transformation = transform_response.transformation

        # Get correlation_id from session_state
        session_state = ctx.message.session_state or {}
        correlation_id = session_state.get("route_correlation_id")

        if not correlation_id:
            logging.error("Received TransformResponse without correlation_id in session_state")
            ctx.send(
                TextFormat(
                    text="**Internal Error**: Received transformation but lost track of the route request.",
                    title="Error",
                )
            )
            return

        # Retrieve pending route context
        route_context = self._pending_routes.get(correlation_id)
        if not route_context:
            logging.error(f"No pending route found for correlation_id: {correlation_id}")
            ctx.send(
                TextFormat(
                    text="**Internal Error**: Could not find pending route request.",
                    title="Error",
                )
            )
            return

        # Remove from pending
        del self._pending_routes[correlation_id]

        # Add transformation to routing rule
        routing_rule = route_context["routing_rule"]
        routing_rule["transformer"] = transformation.model_dump()

        # Send the completed route
        route_response = RouteResponse(
            routing_rule=routing_rule,
            explanation=route_context["explanation"] + f"\n\nTransformation: {transform_response.explanation}",
        )
        ctx.send(route_response)

        logging.info(f"Completed route with transformation for correlation_id: {correlation_id}")

    def _build_route_async(
        self,
        ctx: ProcessContext,
        llm: LLM,
        user_prompt: str,
        source_agent_name: str,
        target_agent_name: str,
        transformation_requirements: str
    ):
        """
        Build a routing rule using the LLM, with async transformation support.

        This method generates the base routing rule, then checks if transformation
        is needed. If so, it sends a TransformRequest to TransformationBuilder
        and stores the route context for later completion.
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

                routing_rule = result.get("routing_rule", {})
                explanation = result.get("explanation", "")
                source_format = result.get("source_format", "")
                target_format = result.get("target_format", "")

                # If formats not provided by LLM, try to look them up
                if not source_format or not target_format:
                    source_formats, _ = self._get_agent_formats(source_agent_name)
                    _, target_formats = self._get_agent_formats(target_agent_name)

                    source_format, target_format, _ = self._select_best_format_pair(
                        source_formats, target_formats
                    )

                # Check if transformation is needed
                if source_format and target_format and self._needs_transformation(source_format, target_format):
                    # Generate correlation ID for tracking
                    correlation_id = str(uuid.uuid4())

                    # Store route context for later completion
                    self._pending_routes[correlation_id] = {
                        "routing_rule": routing_rule,
                        "explanation": explanation,
                        "source_agent": source_agent_name,
                        "target_agent": target_agent_name,
                    }

                    # Send transformation request to TransformationBuilder
                    transform_request = TransformRequest(
                        source_format=source_format,
                        target_format=target_format,
                        source_agent_name=source_agent_name,
                        target_agent_name=target_agent_name,
                        requirements=transformation_requirements,
                    )

                    # Add correlation_id to session_state so TransformResponse can find the pending route
                    ctx.update_context({"route_correlation_id": correlation_id})

                    ctx.send(transform_request)

                    logging.info(
                        f"Sent TransformRequest for {source_format} → {target_format} "
                        f"with correlation_id: {correlation_id}"
                    )
                else:
                    # No transformation needed - send route directly
                    route_response = RouteResponse(
                        routing_rule=routing_rule,
                        explanation=explanation,
                    )
                    ctx.send(route_response)

                    logging.info(f"Created route without transformation: {source_format} → {target_format}")

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

    def _build_route_with_transformation(
        self,
        ctx: ProcessContext,
        llm: LLM,
        user_prompt: str,
        transformation: TransformationSpec
    ):
        """
        Build a routing rule with a pre-provided transformation.

        This is used when RouteRequest already includes a transformation.
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

                routing_rule = result.get("routing_rule", {})
                routing_rule["transformer"] = transformation.model_dump()

                route_response = RouteResponse(
                    routing_rule=routing_rule,
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
