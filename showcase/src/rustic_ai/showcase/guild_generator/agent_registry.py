"""
Agent Registry Agent for the Guild Generator.

This agent maintains knowledge of available agent types in the framework
and can suggest appropriate agents based on user requirements.
"""

import json
import logging
import re
from typing import Any, Dict, List

from pydantic import Field

from rustic_ai.core.agents.commons.message_formats import ErrorMessage
from rustic_ai.core.guild.agent import Agent, ProcessContext, processor
from rustic_ai.core.guild.dsl import BaseAgentProps
from rustic_ai.core.guild.agent_ext.depends.llm.llm import LLM
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    SystemMessage,
    UserMessage,
)
from rustic_ai.showcase.guild_generator.models import (
    AgentLookupRequest,
    AgentLookupResponse,
    AgentRegistryInfo,
    OrchestratorAction,
    ActionType,
)


# Registry of available agent types
AGENT_REGISTRY: List[AgentRegistryInfo] = [
    AgentRegistryInfo(
        class_name="rustic_ai.llm_agent.llm_agent.LLMAgent",
        name="LLMAgent",
        description="A general-purpose LLM agent that processes ChatCompletionRequest and returns ChatCompletionResponse. "
        "Can be configured with custom system prompts. Great for text generation, summarization, translation, Q&A.",
        input_formats=["rustic_ai.core.guild.agent_ext.depends.llm.models.ChatCompletionRequest"],
        output_formats=["rustic_ai.core.guild.agent_ext.depends.llm.models.ChatCompletionResponse"],
        required_dependencies={},
        example_properties={
            "default_system_prompt": "You are a helpful assistant.",
            "send_response": True,
        },
    ),
    AgentRegistryInfo(
        class_name="rustic_ai.core.agents.eip.splitter_agent.SplitterAgent",
        name="SplitterAgent",
        description="Splits a single message into multiple messages using a JSONata expression. "
        "Useful for breaking down lists, arrays, or complex data into individual items.",
        input_formats=["any"],
        output_formats=["configurable"],
        required_dependencies={},
        example_properties={
            "splitter": {"split_type": "jsonata", "expression": "$map($.items, function($v){ $v })"},
            "format_selector": {"strategy": "fixed", "fixed_format": "output_format_class"},
        },
    ),
    AgentRegistryInfo(
        class_name="rustic_ai.core.agents.eip.aggregating_agent.AggregatingAgent",
        name="AggregatingAgent",
        description="Aggregates multiple messages into a single message. "
        "Useful for collecting results from parallel processing.",
        input_formats=["any"],
        output_formats=["configurable"],
        required_dependencies={},
        example_properties={},
    ),
    AgentRegistryInfo(
        class_name="rustic_ai.llm_agent.react.react_agent.ReactAgent",
        name="ReactAgent",
        description="A ReAct (Reasoning + Acting) agent that can use tools. "
        "Great for complex tasks requiring multiple steps, tool usage, or external API calls.",
        input_formats=["rustic_ai.core.guild.agent_ext.depends.llm.models.ChatCompletionRequest"],
        output_formats=["rustic_ai.core.guild.agent_ext.depends.llm.models.ChatCompletionResponse"],
        required_dependencies={},
        example_properties={
            "default_system_prompt": "You are a helpful assistant with tools.",
            "toolsets": [],
        },
    ),
    AgentRegistryInfo(
        class_name="rustic_ai.core.agents.testutils.echo_agent.EchoAgent",
        name="EchoAgent",
        description="A simple agent that echoes back the input. Useful for testing and debugging.",
        input_formats=["any"],
        output_formats=["same as input"],
        required_dependencies={},
        example_properties={},
    ),
]


class AgentRegistryAgentProps(BaseAgentProps):
    """Properties for the AgentRegistryAgent."""

    system_prompt: str = Field(
        default="""You are an agent registry expert for the Rustic AI framework. Given a user's description
of what they need an agent to do, you must select the most appropriate agent type and generate
a complete AgentSpec configuration.

Available agent types:
{agent_registry}

Your task:
1. Analyze the user's requirements
2. Select the most appropriate agent type
3. Generate an AgentSpec JSON with ONLY these fields (no other fields allowed):
   - id: A unique snake_case identifier
   - name: A human-readable name
   - description: What this specific agent instance does
   - class_name: The full class path of the agent (must be one from the available types above)
   - additional_topics: List of topics to subscribe to (usually empty list [])
   - properties: Agent-specific configuration (use example_properties as reference)
   - listen_to_default_topic: Usually true unless specifically listening to custom topics
   - act_only_when_tagged: Whether the agent should only respond when tagged (usually false)

IMPORTANT: Do NOT include dependency_map, guild_spec, or any other fields not listed above.
Dependencies will be provided by the guild automatically.

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
    "explanation": "<brief explanation of why this agent was chosen>"
}}"""
    )


class AgentRegistryAgent(Agent[AgentRegistryAgentProps]):
    """
    Agent Registry that knows available agent types and suggests appropriate ones.

    When it receives an OrchestratorAction with action=add_agent, it uses an LLM
    to select and configure the appropriate agent based on the user's requirements.
    """

    def _get_registry_description(self) -> str:
        """Generate a description of available agents for the LLM prompt."""
        descriptions = []
        for agent in AGENT_REGISTRY:
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

    def _extract_json_from_response(self, response_text: str) -> str:
        """
        Extract JSON from response text that may be wrapped in markdown code blocks.
        """
        text = response_text.strip()

        # Try to find JSON in markdown code blocks
        code_block_pattern = r"```(?:json)?\s*\n?([\s\S]*?)\n?```"
        matches = re.findall(code_block_pattern, text)
        if matches:
            # Return the first code block content
            return matches[0].strip()

        # If no code blocks, try to find JSON object directly
        # Look for content starting with { and ending with }
        json_pattern = r"(\{[\s\S]*\})"
        matches = re.findall(json_pattern, text)
        if matches:
            return matches[0].strip()

        # Return original text if no patterns match
        return text

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
        agent_type_hint = details.get("agent_type_hint", "")

        # Build the prompt
        system_prompt = self.config.system_prompt.format(agent_registry=self._get_registry_description())

        user_prompt = f"""User wants an agent with these requirements:
Purpose: {purpose}
Type hint (if any): {agent_type_hint}

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
                json_text = self._extract_json_from_response(response_text)
                result = json.loads(json_text)
                agent_spec = result.get("agent_spec", {})

                # Look up the agent's message formats from the registry
                input_formats, output_formats = self._get_message_formats(agent_spec.get("class_name", ""))

                agent_response = AgentLookupResponse(
                    agent_spec=agent_spec,
                    explanation=result.get("explanation", ""),
                    available_agents=AGENT_REGISTRY,
                    input_formats=input_formats,
                    output_formats=output_formats,
                )
                ctx.send(agent_response)

            except json.JSONDecodeError as e:
                logging.error(f"Failed to parse agent lookup response: {response_text}")
                ctx.send_error(
                    ErrorMessage(
                        agent_type="AgentRegistryAgent",
                        error_type="JSONDecodeError",
                        error_message=f"Invalid JSON response: {str(e)}",
                    )
                )

        except Exception as e:
            logging.error(f"Error in agent lookup: {e}")
            ctx.send_error(
                ErrorMessage(
                    agent_type="AgentRegistryAgent",
                    error_type=type(e).__name__,
                    error_message=str(e),
                )
            )

    def _get_message_formats(self, class_name: str) -> tuple[List[str], List[str]]:
        """Look up the agent's message formats from the registry."""
        for registry_agent in AGENT_REGISTRY:
            if registry_agent.class_name == class_name:
                return registry_agent.input_formats, registry_agent.output_formats
        return [], []

    @processor(AgentLookupRequest, depends_on=["llm"])
    def handle_direct_lookup(self, ctx: ProcessContext[AgentLookupRequest], llm: LLM):
        """
        Handle direct agent lookup requests (not from orchestrator).
        """
        request = ctx.payload

        system_prompt = self.config.system_prompt.format(agent_registry=self._get_registry_description())

        user_prompt = f"""User wants an agent with these requirements:
Purpose: {request.description}
Input format (if specified): {request.input_format or 'Not specified'}
Output format (if specified): {request.output_format or 'Not specified'}

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
                json_text = self._extract_json_from_response(response_text)
                result = json.loads(json_text)
                agent_spec = result.get("agent_spec", {})

                # Look up the agent's message formats from the registry
                input_formats, output_formats = self._get_message_formats(agent_spec.get("class_name", ""))

                agent_response = AgentLookupResponse(
                    agent_spec=agent_spec,
                    explanation=result.get("explanation", ""),
                    available_agents=AGENT_REGISTRY,
                    input_formats=input_formats,
                    output_formats=output_formats,
                )
                ctx.send(agent_response)

            except json.JSONDecodeError as e:
                logging.error(f"Failed to parse agent lookup response: {response_text}")
                ctx.send_error(
                    ErrorMessage(
                        agent_type="AgentRegistryAgent",
                        error_type="JSONDecodeError",
                        error_message=f"Invalid JSON response: {str(e)}",
                    )
                )

        except Exception as e:
            logging.error(f"Error in agent lookup: {e}")
            ctx.send_error(
                ErrorMessage(
                    agent_type="AgentRegistryAgent",
                    error_type=type(e).__name__,
                    error_message=str(e),
                )
            )
