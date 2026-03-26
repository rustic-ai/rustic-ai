"""
Orchestrator Agent for the Guild Generator.

This agent is the main entry point for user commands. It interprets user
intent when tagged with @Orchestrator and produces action commands that
are routed to the appropriate downstream agents.
"""

import json
import logging
import re
from typing import Optional

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
from rustic_ai.showcase.guild_generator.models import ActionType, OrchestratorAction


class OrchestratorAgentProps(BaseAgentProps):
    """Properties for the OrchestratorAgent."""

    system_prompt: str = Field(
        default="""You are the Orchestrator for a Guild Generator. Your job is to interpret user commands
and decide what action to take. Users tag you with @Orchestrator to modify the guild they are building.

Available actions:
- add_agent: Add a new agent to the guild. Extract the agent description/purpose.
- add_route: Add a routing rule between agents. Extract source agent, target agent, and any transformation needs.
- remove_agent: Remove an agent from the guild. Extract the agent name/id.
- remove_route: Remove a routing rule. Extract the route identifier.
- test_flow: Test the current guild flow with a sample message.
- show_flow: Show the current flowchart visualization.
- publish: Export the final guild specification.
- help: Show help information.
- set_name: Set the guild name.
- set_description: Set the guild description.

Respond ONLY with a JSON object in this exact format:
{
    "action": "<action_type>",
    "details": {<relevant details extracted from user message>},
    "user_message": "<original user message>"
}

Examples:

User: "@Orchestrator add an LLM agent that summarizes text"
Response: {"action": "add_agent", "details": {"purpose": "summarizes text", "agent_type_hint": "LLM"}, "user_message": "@Orchestrator add an LLM agent that summarizes text"}

User: "@Orchestrator connect the summarizer output to the formatter input"
Response: {"action": "add_route", "details": {"source_agent": "summarizer", "target_agent": "formatter"}, "user_message": "@Orchestrator connect the summarizer output to the formatter input"}

User: "@Orchestrator show me the current flow"
Response: {"action": "show_flow", "details": {}, "user_message": "@Orchestrator show me the current flow"}

User: "@Orchestrator name this guild 'Text Processing Pipeline'"
Response: {"action": "set_name", "details": {"name": "Text Processing Pipeline"}, "user_message": "@Orchestrator name this guild 'Text Processing Pipeline'"}

Always respond with valid JSON only. No additional text."""
    )


class OrchestratorAgent(Agent[OrchestratorAgentProps]):
    """
    Orchestrator agent that interprets user commands and routes them.

    This agent is activated only when tagged with @Orchestrator.
    It uses an LLM to interpret the user's intent and produce
    an OrchestratorAction that gets routed to downstream agents.
    """

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

    @processor(ChatCompletionRequest, depends_on=["llm"])
    def process_command(self, ctx: ProcessContext[ChatCompletionRequest], llm: LLM):
        """
        Process a user command and produce an action.

        The user message is analyzed by the LLM to determine the appropriate
        action and extract relevant details.
        """
        request = ctx.payload

        # Extract the user message
        user_message = ""
        for msg in request.messages:
            if isinstance(msg, UserMessage):
                if isinstance(msg.content, str):
                    user_message = msg.content
                else:
                    # Handle content parts
                    for part in msg.content.root or []:
                        if hasattr(part, "text"):
                            user_message = part.text
                            break

        # Build the LLM request with our system prompt
        llm_request = ChatCompletionRequest(
            messages=[
                SystemMessage(content=self.config.system_prompt),
                UserMessage(content=user_message),
            ]
        )

        try:
            # Call the LLM
            response: ChatCompletionResponse = llm.completion(llm_request)

            # Extract the response content
            response_text = response.choices[0].message.content

            # Parse the JSON response (extract from markdown if needed)
            try:
                json_text = self._extract_json_from_response(response_text)
                action_data = json.loads(json_text)
                action = OrchestratorAction(
                    action=ActionType(action_data.get("action", "help")),
                    details=action_data.get("details", {}),
                    user_message=action_data.get("user_message", user_message),
                )
                ctx.send(action)

            except json.JSONDecodeError as e:
                logging.error(f"Failed to parse LLM response as JSON: {response_text}")
                # Send a help action if we can't parse
                ctx.send(
                    OrchestratorAction(
                        action=ActionType.HELP,
                        details={"error": f"Could not parse response: {str(e)}"},
                        user_message=user_message,
                    )
                )

        except Exception as e:
            logging.error(f"Error processing orchestrator command: {e}")
            ctx.send_error(
                ErrorMessage(
                    agent_type="OrchestratorAgent",
                    error_type=type(e).__name__,
                    error_message=f"{str(e)} | user_message: {user_message}",
                )
            )
