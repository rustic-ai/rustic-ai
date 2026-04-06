"""
Guild Export Agent for the Guild Generator.

This agent assembles and validates the final guild specification,
collecting agents and routes from guild state to create a complete
GuildSpec JSON that can be used to deploy the guild.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from pydantic import Field, ValidationError

from rustic_ai.core.guild import AgentSpec
from rustic_ai.core.guild.dsl import BaseAgentProps
from rustic_ai.core.guild.dsl import GuildSpec
from rustic_ai.core.guild.agent import Agent, ProcessContext, processor
from rustic_ai.core.messaging.core.message import RoutingRule, RoutingSlip
from rustic_ai.core.ui_protocol.types import TextFormat
from rustic_ai.showcase.guild_generator.models import (
    ActionType,
    ExportRequest,
    ExportResponse,
    GuildBuilderState,
    OrchestratorAction,
)


class GuildExportAgentProps(BaseAgentProps):
    """Properties for the GuildExportAgent."""

    include_comments: bool = Field(default=True)


class GuildExportAgent(Agent[GuildExportAgentProps]):
    """
    Agent that assembles and validates the final guild specification.

    This agent reads the guild_builder state and creates a complete
    GuildSpec that can be exported as JSON for deployment.
    """

    def _extract_guild_state(self, ctx: ProcessContext) -> Optional[GuildBuilderState]:
        """Extract the guild builder state from the guild state (updated by routing rules)."""
        # First try guild state (where guild_state_update in routes writes to)
        guild_state = self.get_guild_state() or {}
        guild_builder = guild_state.get("guild_builder", {})

        # Fallback to session_state for backwards compatibility
        if not guild_builder:
            session_state = ctx.message.session_state or {}
            guild_builder = session_state.get("guild_builder", {})

        if guild_builder:
            return GuildBuilderState.model_validate(guild_builder)
        return GuildBuilderState()

    def _validate_agent_spec(self, agent_dict: Dict[str, Any]) -> List[str]:
        """Validate an agent specification."""
        errors = []

        required_fields = ["id", "name", "description", "class_name"]
        for field in required_fields:
            if not agent_dict.get(field):
                errors.append(f"Agent missing required field: {field}")

        # Validate class_name format
        class_name = agent_dict.get("class_name", "")
        if class_name and "." not in class_name:
            errors.append(f"Invalid class_name format: {class_name} (should be fully qualified)")

        return errors

    def _validate_routing_rule(self, route_dict: Dict[str, Any]) -> List[str]:
        """Validate a routing rule."""
        errors = []

        # Must have either agent or agent_type
        if not route_dict.get("agent") and not route_dict.get("agent_type"):
            errors.append("Route must have either 'agent' or 'agent_type'")

        # Should have message_format for most routes
        if not route_dict.get("message_format"):
            errors.append("Route missing message_format (recommended for explicit routing)")

        # Validate transformer if present
        transformer = route_dict.get("transformer")
        if transformer:
            if not transformer.get("handler") and not transformer.get("expression"):
                errors.append("Transformer must have either 'handler' or 'expression'")

            style = transformer.get("style", "simple")
            if style == "simple" and not transformer.get("output_format"):
                # Warning, not error
                pass
            elif style == "content_based_router" and not transformer.get("handler"):
                errors.append("content_based_router transformer must have 'handler'")

        return errors

    def _build_guild_spec(
        self, guild_state: GuildBuilderState
    ) -> tuple[Dict[str, Any], List[str]]:
        """
        Build a complete GuildSpec from the guild state.

        Returns the spec dict and a list of validation errors.
        """
        errors = []

        # Validate agents
        for i, agent_dict in enumerate(guild_state.agents):
            agent_errors = self._validate_agent_spec(agent_dict)
            for error in agent_errors:
                errors.append(f"Agent {i} ({agent_dict.get('name', 'unnamed')}): {error}")

        # Validate routes
        for i, route_dict in enumerate(guild_state.routes):
            route_errors = self._validate_routing_rule(route_dict)
            for error in route_errors:
                errors.append(f"Route {i}: {error}")

        # Build the spec
        spec = {
            "name": guild_state.name,
            "description": guild_state.description,
            "properties": {},
            "agents": guild_state.agents,
            "routes": {"steps": guild_state.routes},
            "dependency_map": {},
        }

        return spec, errors

    @processor(
        OrchestratorAction,
        predicate=lambda self, msg: msg.payload.get("action") == ActionType.PUBLISH,
    )
    def handle_publish_action(self, ctx: ProcessContext[OrchestratorAction]):
        """
        Handle publish action from the orchestrator.
        """
        guild_state = self._extract_guild_state(ctx)

        if not guild_state.agents:
            # Send a message indicating no agents to export
            ctx.send(
                TextFormat(
                    text="**Cannot export guild:** No agents have been added yet.\n\n"
                    "Use `@Orchestrator add an agent that...` to add agents first.",
                    title="Export Failed",
                )
            )
            return

        spec, errors = self._build_guild_spec(guild_state)

        if errors:
            error_text = "**Validation Errors:**\n" + "\n".join(f"- {e}" for e in errors)
            ctx.send(
                TextFormat(
                    text=f"Guild has validation issues:\n\n{error_text}\n\n"
                    "Fix these issues before exporting.",
                    title="Validation Errors",
                )
            )

        # Export even if there are warnings
        json_output = json.dumps(spec, indent=2)

        response = ExportResponse(
            guild_spec=spec,
            is_valid=len(errors) == 0,
            validation_errors=errors,
            json_output=json_output,
        )

        ctx.send(response)

        # Also send a text version for display
        ctx.send(
            TextFormat(
                text=f"**Guild Specification**\n\n```json\n{json_output}\n```\n\n"
                + (
                    "Guild is ready for deployment!"
                    if not errors
                    else f"**Note:** {len(errors)} validation issues found."
                ),
                title=f"Exported: {guild_state.name}",
            )
        )

    @processor(ExportRequest)
    def handle_export_request(self, ctx: ProcessContext[ExportRequest]):
        """
        Handle direct export requests.
        """
        request = ctx.payload
        guild_state = self._extract_guild_state(ctx)

        spec, errors = self._build_guild_spec(guild_state)

        json_output = json.dumps(spec, indent=2)

        response = ExportResponse(
            guild_spec=spec,
            is_valid=len(errors) == 0 if request.run_validation else True,
            validation_errors=errors if request.run_validation else [],
            json_output=json_output,
        )

        ctx.send(response)
