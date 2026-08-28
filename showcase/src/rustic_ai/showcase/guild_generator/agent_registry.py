"""
Agent Registry Agent for the Guild Generator.

This agent maintains knowledge of available agent types in the framework
and can suggest appropriate agents based on user requirements.
"""

import json
import logging
import os
import time
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
from rustic_ai.showcase.guild_generator.constants import (
    AGENT_TYPE_KEYWORDS,
    AGGREGATING_AGENT_CLASS,
    API_MAX_RETRIES,
    API_RETRY_BACKOFF_FACTOR,
    API_RETRY_INITIAL_DELAY,
    API_TIMEOUT_SECONDS,
    LLM_AGENT_CLASS,
    MAX_AGENTS_IN_ERROR_MESSAGE,
    REACT_AGENT_CLASS,
    SPLITTER_AGENT_CLASS,
)
from rustic_ai.showcase.guild_generator.models import (
    AgentLookupRequest,
    AgentLookupResponse,
    AgentRegistryInfo,
    OrchestratorAction,
    ActionType,
)
from rustic_ai.showcase.guild_generator.utils import extract_json_from_response


class AgentRegistryAgentProps(BaseAgentProps):
    """Properties for the AgentRegistryAgent."""

    api_base_url: str = Field(
        default_factory=lambda: os.getenv("RUSTIC_AI_FORGE_API_URL", "http://localhost:3001"),
        description="Base URL of the API server to fetch agents from."
    )

    system_prompt: str = Field(
        default="""You are an agent registry expert for the Rustic AI framework. Given a user's description
of what they need an agent to do, you MUST select the most appropriate agent type from the available
agents registry and generate a complete AgentSpec configuration.

CRITICAL CONSTRAINT: You can ONLY use agents that exist in the registry below. You CANNOT create
new agent types or suggest agents that are not listed. If there is no perfect match, choose the
closest available agent from the registry that can fulfill the requirements.

Available agent types:
{agent_registry}

Your task:
1. Analyze the user's requirements
2. Select the most appropriate agent type FROM THE REGISTRY ABOVE (no exceptions)
3. Generate an AgentSpec JSON with ONLY these fields (no other fields allowed):
   - id: A unique snake_case identifier
   - name: A human-readable name
   - description: What this specific agent instance does
   - class_name: The full class path of the agent (MUST be exactly one of the class_name values from the registry above)
   - additional_topics: List of topics to subscribe to (usually empty list [])
   - properties: Agent-specific configuration (use example_properties as reference)
   - listen_to_default_topic: Usually true unless specifically listening to custom topics
   - act_only_when_tagged: Whether the agent should only respond when tagged (usually false)

IMPORTANT RULES:
- Do NOT include dependency_map, guild_spec, or any other fields not listed above
- Dependencies will be provided by the guild automatically
- The class_name field MUST exactly match one of the class_name values from the available agent types
- You cannot create new agent types - only select from what exists in the registry
- If the user requests something that doesn't exist, pick the closest match and explain the limitation
- Copy the class_name EXACTLY character-for-character from the registry - no abbreviations, no modifications

EXAMPLES of correct class_name usage:
✓ CORRECT: "class_name": "rustic_ai.llm_agent.llm_agent.LLMAgent"
✓ CORRECT: "class_name": "rustic_ai.core.agents.eip.splitter_agent.SplitterAgent"
✓ CORRECT: "class_name": "rustic_ai.llm_agent.react.react_agent.ReActAgent"

✗ WRONG: "class_name": "rustic_ai.agents.llm.LLMAgent" (path doesn't exist)
✗ WRONG: "class_name": "rustic_ai.agents.llm.LLMSummarizerAgent" (agent doesn't exist)
✗ WRONG: "class_name": "LLMAgent" (missing full module path)

Respond ONLY with a JSON object in this exact format:
{{
    "agent_spec": {{
        "id": "...",
        "name": "...",
        "description": "...",
        "class_name": "...",
        "additional_topics": [],
        "properties": {{}},
        "listen_to_default_topic": true,
        "act_only_when_tagged": false
    }},
    "explanation": "<brief explanation of why this agent was chosen from the registry>"
}}"""
    )


class AgentRegistryAgent(Agent[AgentRegistryAgentProps]):
    """
    Agent Registry that knows available agent types and suggests appropriate ones.

    When it receives an OrchestratorAction with action=add_agent, it uses an LLM
    to select and configure the appropriate agent based on the user's requirements.

    The agent registry is fetched from the API during initialization and cached.
    """

    def __init__(self):
        """Initialize agent with lazy loading for agent catalog."""
        self._agents: Optional[List[AgentRegistryInfo]] = None
        self._fetch_attempted: bool = False

    def _ensure_agents_loaded(self) -> None:
        """Ensure agents are loaded from API (lazy loading)."""
        if self._agents is None and not self._fetch_attempted:
            self._fetch_attempted = True
            self._fetch_agents_from_api()

    def _fetch_agents_from_api(self) -> None:
        """
        Fetch agents from API with retry logic.

        Uses exponential backoff for transient failures.
        """
        url = f"{self.config.api_base_url.rstrip('/')}/catalog/agents"
        last_exception = None

        for attempt in range(API_MAX_RETRIES):
            try:
                if attempt > 0:
                    delay = API_RETRY_INITIAL_DELAY * (API_RETRY_BACKOFF_FACTOR ** (attempt - 1))
                    logging.info(f"Retrying API request (attempt {attempt + 1}/{API_MAX_RETRIES}) after {delay:.1f}s...")
                    time.sleep(delay)

                logging.info(f"Fetching agent catalog from {url}")
                response = httpx.get(url, timeout=API_TIMEOUT_SECONDS)
                response.raise_for_status()
                data = response.json()
                self._agents = self._parse_agent_data(data)
                logging.info(f"Successfully loaded {len(self._agents)} agents from API")
                return

            except httpx.TimeoutException as e:
                last_exception = e
                logging.warning(f"API request timed out (attempt {attempt + 1}/{API_MAX_RETRIES}): {e}")
            except httpx.HTTPStatusError as e:
                # Don't retry 4xx errors (client errors)
                if 400 <= e.response.status_code < 500:
                    logging.error(f"Client error from API (no retry): {e}")
                    last_exception = e
                    break
                # Retry 5xx errors (server errors)
                last_exception = e
                logging.warning(f"Server error from API (attempt {attempt + 1}/{API_MAX_RETRIES}): {e}")
            except Exception as e:
                last_exception = e
                logging.warning(f"Failed to fetch agents from API (attempt {attempt + 1}/{API_MAX_RETRIES}): {e}")

        # All retries failed
        logging.error(f"Failed to fetch agents from {url} after {API_MAX_RETRIES} attempts: {last_exception}")
        self._agents = []
        raise RuntimeError(
            f"Agent registry could not be loaded from API at {url} after {API_MAX_RETRIES} attempts. "
            f"Ensure the API server is running and accessible. Error: {last_exception}"
        )

    def _parse_agent_data(self, data: Dict[str, Any]) -> List[AgentRegistryInfo]:
        """Parse agent data from API response into AgentRegistryInfo objects."""

        agents = []
        for class_name, agent_data in data.items():
            input_formats = []
            output_formats = []

            handlers = agent_data.get("message_handlers", {})
            for handler in handlers.values():
                in_fmt = handler.get("message_format")
                if in_fmt:
                    input_formats.append(in_fmt)

                for output_call in handler.get("send_message_calls", []):
                    if output_call and isinstance(output_call, dict):
                        out_fmt = output_call.get("message_type")
                        if out_fmt:
                            output_formats.append(out_fmt)

            # Deduplicate while preserving order
            input_formats = list(dict.fromkeys(input_formats))
            output_formats = list(dict.fromkeys(output_formats))

            if not input_formats:
                input_formats = ["any"]
            if not output_formats:
                output_formats = ["configurable"]

            # Try to build example properties purely from schema defaults
            example_properties = {}
            schema = agent_data.get("agent_props_schema", {})
            properties = schema.get("properties", {})
            for prop_name, prop_details in properties.items():
                if isinstance(prop_details, dict) and "default" in prop_details:
                    example_properties[prop_name] = prop_details["default"]

            req_deps = agent_data.get("agent_dependencies", {})
            if not isinstance(req_deps, dict):
                req_deps = {}

            agents.append(
                AgentRegistryInfo(
                    class_name=agent_data.get("qualified_class_name", class_name),
                    name=agent_data.get("agent_name", class_name.split(".")[-1]),
                    description=agent_data.get("agent_doc", ""),
                    input_formats=input_formats,
                    output_formats=output_formats,
                    required_dependencies=req_deps,
                    example_properties=example_properties,
                )
            )

        return agents

    def _get_agents(self) -> List[AgentRegistryInfo]:
        """Get cached agents list, loading from API if needed."""
        self._ensure_agents_loaded()
        if self._agents is None:
            raise RuntimeError(
                "Agent registry could not be loaded from API. "
                "Check API server availability and configuration."
            )
        return self._agents

    def _get_registry_description(self) -> str:
        """Generate a description of available agents for the LLM prompt."""
        descriptions = []
        for agent in self._get_agents():
            desc = f"""
- {agent.name} ({agent.class_name})
  Description: {agent.description}
  Input formats: {', '.join(agent.input_formats)}
  Output formats: {', '.join(agent.output_formats)}
  Required dependencies: {json.dumps(agent.required_dependencies) if agent.required_dependencies else 'None'}
  Example properties: {json.dumps(agent.example_properties) if agent.example_properties else 'None'}
"""
            descriptions.append(desc)
        return "\n".join(descriptions)

    def _get_message_formats(self, class_name: str) -> tuple[List[str], List[str]]:
        """Look up the agent's message formats from the registry."""
        for registry_agent in self._get_agents():
            if registry_agent.class_name == class_name:
                return registry_agent.input_formats, registry_agent.output_formats
        return [], []

    def _get_agent_type_suggestions(self, text: str) -> List[str]:
        """
        Get agent type suggestions based on keywords in the text.

        Args:
            text: User's description or purpose for the agent

        Returns:
            List of suggested agent class names
        """
        suggestions = []
        text_lower = text.lower()
        for keyword, agent_classes in AGENT_TYPE_KEYWORDS.items():
            if keyword in text_lower:
                suggestions.extend(agent_classes)

        # Deduplicate while preserving order
        return list(dict.fromkeys(suggestions))

    def _validate_and_format_agent_spec(
        self,
        ctx: ProcessContext,
        result: Dict[str, Any],
        request_context: str
    ) -> Optional[AgentLookupResponse]:
        """
        Validate an agent spec from LLM response and create AgentLookupResponse.

        Args:
            ctx: Process context for sending error messages
            result: Parsed JSON result from LLM
            request_context: Original request text for error messages

        Returns:
            AgentLookupResponse if valid, None if validation fails
        """
        agent_spec = result.get("agent_spec", {})

        # Validate: Ensure the class_name exists in the registry
        class_name = agent_spec.get("class_name", "")
        valid_class_names = [agent.class_name for agent in self._get_agents()]

        if class_name not in valid_class_names:
            suggestions = self._get_agent_type_suggestions(request_context)
            suggestion_text = (
                f"Suggested alternatives: {', '.join(suggestions)}"
                if suggestions
                else f"Available agents include: {', '.join(valid_class_names[:MAX_AGENTS_IN_ERROR_MESSAGE])}"
            )

            error_msg = (
                f"Invalid agent class '{class_name}' - this agent type does not exist in the registry. "
                f"Original request: '{request_context}'. "
                f"{suggestion_text}. "
                f"Please select from available agents only."
            )
            logging.error(error_msg)

            # Send error to user
            ctx.send(
                TextFormat(
                    text=f"**Agent Creation Failed**\n\n{error_msg}",
                    title="Error",
                )
            )
            # Also send error message for system handling
            ctx.send_error(
                ErrorMessage(
                    agent_type="AgentRegistryAgent",
                    error_type="ValidationError",
                    error_message=error_msg,
                )
            )
            return None

        # Look up the agent's message formats from the registry
        input_formats, output_formats = self._get_message_formats(class_name)

        return AgentLookupResponse(
            agent_spec=agent_spec,
            explanation=result.get("explanation", ""),
            available_agents=self._get_agents(),
            input_formats=input_formats,
            output_formats=output_formats,
        )

    def _call_llm_for_agent_lookup(
        self,
        ctx: ProcessContext,
        llm: LLM,
        purpose: str,
        input_format: Optional[str] = None,
        output_format: Optional[str] = None
    ) -> None:
        """
        Call LLM to get agent recommendation and send response.

        Args:
            ctx: Process context
            llm: LLM instance
            purpose: What the agent should do
            input_format: Optional expected input format
            output_format: Optional expected output format
        """
        system_prompt = self.config.system_prompt.format(
            agent_registry=self._get_registry_description()
        )

        user_prompt = f"""User wants an agent with these requirements:
Purpose: {purpose}"""

        if input_format:
            user_prompt += f"\nInput format (if specified): {input_format}"
        if output_format:
            user_prompt += f"\nOutput format (if specified): {output_format}"

        user_prompt += """

CRITICAL: You MUST select the class_name EXACTLY as it appears in the available agent types list above.
Do NOT modify, abbreviate, or create new class names. Copy the class_name field character-for-character.

Please select the most appropriate agent and generate a complete AgentSpec configuration."""

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

                # Validate and create response
                agent_response = self._validate_and_format_agent_spec(
                    ctx=ctx,
                    result=result,
                    request_context=purpose
                )

                if agent_response:
                    ctx.send(agent_response)

            except json.JSONDecodeError as e:
                logging.error(f"Failed to parse agent lookup response: {response_text}")
                ctx.send(
                    TextFormat(
                        text=f"**Failed to parse LLM response**\n\nThe LLM did not return valid JSON. Please try again.\n\nError: {str(e)}",
                        title="Parse Error",
                    )
                )
                ctx.send_error(
                    ErrorMessage(
                        agent_type="AgentRegistryAgent",
                        error_type="JSONDecodeError",
                        error_message=f"Invalid JSON response: {str(e)}",
                    )
                )

        except Exception as e:
            logging.error(f"Error in agent lookup: {e}")
            ctx.send(
                TextFormat(
                    text=f"**Agent Lookup Failed**\n\nAn error occurred while looking up agents.\n\nError: {str(e)}",
                    title="Error",
                )
            )
            ctx.send_error(
                ErrorMessage(
                    agent_type="AgentRegistryAgent",
                    error_type=type(e).__name__,
                    error_message=str(e),
                )
            )

    @processor(
        OrchestratorAction,
        predicate=lambda self, msg: msg.payload.get("action") == ActionType.ADD_AGENT,
        depends_on=["llm"],
    )
    def lookup_agent(self, ctx: ProcessContext[OrchestratorAction], llm: LLM):
        """
        Look up an appropriate agent based on the orchestrator action.
        """
        action = ctx.payload
        details = action.details

        # Extract agent requirements from details
        purpose = details.get("purpose", details.get("description", action.user_message))

        self._call_llm_for_agent_lookup(ctx, llm, purpose)

    @processor(AgentLookupRequest, depends_on=["llm"])
    def handle_direct_lookup(self, ctx: ProcessContext[AgentLookupRequest], llm: LLM):
        """
        Handle direct agent lookup requests (not from orchestrator).
        """
        request = ctx.payload

        self._call_llm_for_agent_lookup(
            ctx,
            llm,
            request.description,
            request.input_format,
            request.output_format
        )
