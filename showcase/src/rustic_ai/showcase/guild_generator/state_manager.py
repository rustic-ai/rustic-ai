"""
State Manager Agent for the Guild Generator.

This agent handles updating the guild state with new agents and routes
as they are created by other agents.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from rustic_ai.core.guild.agent import Agent, ProcessContext, processor
from rustic_ai.core.guild.dsl import BaseAgentProps
from rustic_ai.core.ui_protocol.types import TextFormat
from rustic_ai.showcase.guild_generator.models import (
    ActionType,
    AgentLookupResponse,
    AgentMessageInfo,
    FlowchartUpdateRequest,
    GuildBuilderState,
    OrchestratorAction,
    RouteResponse,
)


class StateManagerAgentProps(BaseAgentProps):
    """Properties for the StateManagerAgent."""

    pass


class StateManagerAgent(Agent[StateManagerAgentProps]):
    """
    Agent that manages the guild builder state.

    This agent receives agent specs and routing rules from other agents
    and updates the guild_builder state accordingly.
    """

    @processor(AgentLookupResponse)
    def add_agent_to_state(self, ctx: ProcessContext[AgentLookupResponse]):
        """
        Add a new agent to the guild builder state.
        """
        response = ctx.payload
        agent_spec = response.agent_spec

        if not agent_spec:
            ctx.send(
                TextFormat(
                    text="Failed to add agent: No agent specification provided.",
                    title="Error",
                )
            )
            return

        # Store message format info for the agent (used by route builder)
        agent_id = agent_spec.get("id", "")
        agent_name = agent_spec.get("name", "Unknown")
        agent_class = agent_spec.get("class_name", "")

        # Update session state with agent message info for downstream processors
        agent_msg_info = AgentMessageInfo(
            agent_id=agent_id,
            agent_name=agent_name,
            class_name=agent_class,
            input_formats=response.input_formats,
            output_formats=response.output_formats,
        )
        ctx.update_context({"new_agent_message_info": agent_msg_info.model_dump()})

        agent_type = agent_class.split(".")[-1]

        # Format message types for display
        input_fmts = ", ".join([f.split(".")[-1] for f in response.input_formats]) or "any"
        output_fmts = ", ".join([f.split(".")[-1] for f in response.output_formats]) or "any"

        ctx.send(
            TextFormat(
                text=f"**Added agent:** {agent_name}\n\n"
                f"**Type:** {agent_type}\n\n"
                f"**Accepts:** {input_fmts}\n\n"
                f"**Sends:** {output_fmts}\n\n"
                f"**Explanation:** {response.explanation}\n\n"
                "Use `@Orchestrator show flow` to see the updated guild diagram.",
                title="Agent Added",
            )
        )

        # Request flowchart update
        ctx.send(FlowchartUpdateRequest(trigger="agent_added"))

    @processor(RouteResponse)
    def add_route_to_state(self, ctx: ProcessContext[RouteResponse]):
        """
        Add a new route to the guild builder state.
        """
        response = ctx.payload
        routing_rule = response.routing_rule

        if not routing_rule:
            ctx.send(
                TextFormat(
                    text="Failed to add route: No routing rule provided.",
                    title="Error",
                )
            )
            return

        # Extract source and destination for display
        source = "Unknown"
        if routing_rule.get("agent"):
            source = routing_rule["agent"].get("name") or routing_rule["agent"].get("id", "Unknown")
        elif routing_rule.get("agent_type"):
            source = routing_rule["agent_type"].split(".")[-1]

        dest = routing_rule.get("destination", {})
        target = dest.get("topics", "default_topic") if dest else "default_topic"

        ctx.send(
            TextFormat(
                text=f"**Added route:**\n\n"
                f"**From:** {source}\n"
                f"**To:** {target}\n\n"
                f"**Explanation:** {response.explanation}\n\n"
                "Use `@Orchestrator show flow` to see the updated guild diagram.",
                title="Route Added",
            )
        )

        # Request flowchart update
        ctx.send(FlowchartUpdateRequest(trigger="route_added"))

    @processor(
        OrchestratorAction,
        predicate=lambda self, msg: msg.payload.get("action") == ActionType.HELP,
    )
    def show_help(self, ctx: ProcessContext[OrchestratorAction]):
        """
        Show help information.
        """
        help_text = """
# Guild Generator Help

Welcome to the Guild Generator! This tool helps you build guilds interactively.

## How to Use

Tag **@Orchestrator** to modify your guild:

### Adding Agents
```
@Orchestrator add an LLM agent that summarizes text
@Orchestrator add a splitter agent to process lists
@Orchestrator add an agent for fact-checking
```

### Adding Routes
```
@Orchestrator connect the summarizer to the formatter
@Orchestrator route output from LLM to user
@Orchestrator add a route from splitter to aggregator
```

### Viewing Your Guild
```
@Orchestrator show flow
@Orchestrator show the current guild diagram
```

### Configuring Your Guild
```
@Orchestrator name this guild "My Pipeline"
@Orchestrator set description to "A text processing pipeline"
```

### Exporting
```
@Orchestrator publish
@Orchestrator export the guild
```

## Testing

Send messages **without** tagging @Orchestrator to test your guild flow:
```
Hello, test this message through the pipeline
```

## Tips

1. Start by adding the agents you need
2. Then connect them with routes
3. Use "show flow" to visualize your progress
4. Test with sample messages
5. Export when satisfied!
"""
        ctx.send(
            TextFormat(text=help_text, title="Guild Generator Help")
        )

    @processor(
        OrchestratorAction,
        predicate=lambda self, msg: msg.payload.get("action") == ActionType.SET_NAME,
    )
    def set_guild_name(self, ctx: ProcessContext[OrchestratorAction]):
        """
        Set the guild name.
        """
        action = ctx.payload
        new_name = action.details.get("name", "New Guild")

        ctx.send(
            TextFormat(
                text=f"Guild name set to: **{new_name}**",
                title="Name Updated",
            )
        )

    @processor(
        OrchestratorAction,
        predicate=lambda self, msg: msg.payload.get("action") == ActionType.SET_DESCRIPTION,
    )
    def set_guild_description(self, ctx: ProcessContext[OrchestratorAction]):
        """
        Set the guild description.
        """
        action = ctx.payload
        new_description = action.details.get("description", "")

        ctx.send(
            TextFormat(
                text=f"Guild description set to:\n\n{new_description}",
                title="Description Updated",
            )
        )
