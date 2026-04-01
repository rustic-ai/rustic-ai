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
from rustic_ai.core.state.models import StateUpdateFormat
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

    Uses local state to avoid race conditions when multiple updates come in quickly.
    """

    def _get_local_state(self) -> Dict[str, Any]:
        """Get the local guild builder state."""
        # Initialize on first access
        if not hasattr(self, '_local_guild_builder'):
            guild_state = self.get_guild_state() or {}
            self._local_guild_builder = guild_state.get("guild_builder", {
                "name": "New Guild",
                "description": "A guild created with Guild Generator",
                "agents": [],
                "routes": [],
                "agent_message_info": []
            })
            logging.info(f"StateManagerAgent initialized with {len(self._local_guild_builder.get('agents', []))} agents")
        return self._local_guild_builder

    def _save_local_state(self, ctx: ProcessContext):
        """Save local state to guild state."""
        # Push the entire local state to guild_state - no read, just write
        logging.info(
            f"Saving local guild builder state with {len(self._local_guild_builder.get('agents', []))} agents "
            f"and {len(self._local_guild_builder.get('routes', []))} routes"
        )
        self.update_guild_state(
            ctx=ctx,
            update_format=StateUpdateFormat.JSON_MERGE_PATCH,
            update={"guild_builder": self._local_guild_builder}
        )

    def _generate_routing_suggestions(self, agent_name: str) -> str:
        """
        Generate routing suggestions for a newly added agent.

        Returns a formatted string with routing suggestions, or empty string if none needed.
        """
        routes = self._local_guild_builder.get("routes", [])
        agents = self._local_guild_builder.get("agents", [])

        # Check if this agent has any routes
        has_input_route = False
        has_output_route = False

        for route in routes:
            # Check if agent is a destination
            dest = route.get("destination", {})
            dest_topics = dest.get("topics", "")

            # Check if agent is a source
            source_agent = route.get("agent", {})
            source_name = source_agent.get("name", "")

            if agent_name in str(dest_topics):
                has_input_route = True
            if source_name == agent_name:
                has_output_route = True

        suggestions = []

        # Only provide suggestions if this is one of the first few agents
        # (after many agents are added, suggestions become noise)
        if len(agents) <= 3:
            if not has_input_route:
                suggestions.append(
                    f"• Add input route: `@Orchestrator add route from UserProxyAgent to {agent_name}`"
                )

            if not has_output_route:
                suggestions.append(
                    f"• Add output route: `@Orchestrator add route from {agent_name} to user_message_broadcast`"
                )

        return "\n".join(suggestions) if suggestions else ""

    @processor(AgentLookupResponse)
    def add_agent_to_state(self, ctx: ProcessContext[AgentLookupResponse]):
        """
        Add a new agent to the guild builder state.
        """
        response = ctx.payload
        agent_spec = response.agent_spec

        logging.info(f"Received AgentLookupResponse with agent_spec: {agent_spec}")

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

        # Update LOCAL state first (no read from guild_state, avoids race condition)
        self._get_local_state()

        # Ensure agents and agent_message_info lists exist
        if "agents" not in self._local_guild_builder:
            self._local_guild_builder["agents"] = []
        if "agent_message_info" not in self._local_guild_builder:
            self._local_guild_builder["agent_message_info"] = []

        # Append the new agent spec
        self._local_guild_builder["agents"].append(agent_spec)

        # Append the agent message info
        self._local_guild_builder["agent_message_info"].append(agent_msg_info.model_dump())

        # Push local state to guild_state (write-only, no read)
        self._save_local_state(ctx)

        agent_type = agent_class.split(".")[-1]

        # Format message types for display
        input_fmts = ", ".join([f.split(".")[-1] for f in response.input_formats]) or "any"
        output_fmts = ", ".join([f.split(".")[-1] for f in response.output_formats]) or "any"

        # Generate routing suggestions
        routing_suggestions = self._generate_routing_suggestions(agent_name)

        message_text = (
            f"**Added agent:** {agent_name}\n\n"
            f"**Type:** {agent_type}\n\n"
            f"**Accepts:** {input_fmts}\n\n"
            f"**Sends:** {output_fmts}\n\n"
            f"**Explanation:** {response.explanation}\n\n"
        )

        if routing_suggestions:
            message_text += f"\n**⚠️ Routing Suggestions:**\n{routing_suggestions}\n\n"

        message_text += "Use `@Orchestrator show flow` to see the updated guild diagram."

        ctx.send(
            TextFormat(
                text=message_text,
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

        logging.info(f"Received RouteResponse with routing_rule: {routing_rule}")

        if not routing_rule:
            ctx.send(
                TextFormat(
                    text="Failed to add route: No routing rule provided.",
                    title="Error",
                )
            )
            return

        # Update LOCAL state first (no read from guild_state, avoids race condition)
        self._get_local_state()

        # Ensure routes list exists
        if "routes" not in self._local_guild_builder:
            self._local_guild_builder["routes"] = []

        # Append the new routing rule
        self._local_guild_builder["routes"].append(routing_rule)

        # Push local state to guild_state (write-only, no read)
        self._save_local_state(ctx)

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

    @processor(
        OrchestratorAction,
        predicate=lambda self, msg: msg.payload.get("action") == ActionType.REMOVE_AGENT,
    )
    def remove_agent(self, ctx: ProcessContext[OrchestratorAction]):
        """
        Remove an agent from the guild builder state.
        """
        action = ctx.payload
        agent_name = action.details.get("agent_name", "")

        # Update LOCAL state first (no read from guild_state, avoids race condition)
        guild_builder = self._get_local_state()
        agents = guild_builder.get("agents", [])

        # Find and remove the agent
        removed = False
        new_agents = []
        for agent in agents:
            if agent.get("name") == agent_name or agent.get("id") == agent_name:
                removed = True
            else:
                new_agents.append(agent)

        if removed:
            # Update local state and push to guild_state
            guild_builder["agents"] = new_agents
            self._save_local_state(ctx)

            ctx.send(
                TextFormat(
                    text=f"**Removed agent:** {agent_name}\n\n"
                    "The agent and any associated routes should be reviewed.",
                    title="Agent Removed",
                )
            )
            # Request flowchart update
            ctx.send(FlowchartUpdateRequest(trigger="agent_removed"))
        else:
            ctx.send(
                TextFormat(
                    text=f"**Agent not found:** {agent_name}\n\n"
                    "No agent with that name or ID exists in the guild.",
                    title="Error",
                )
            )

    @processor(
        OrchestratorAction,
        predicate=lambda self, msg: msg.payload.get("action") == ActionType.REMOVE_ROUTE,
    )
    def remove_route(self, ctx: ProcessContext[OrchestratorAction]):
        """
        Remove a route from the guild builder state.
        """
        action = ctx.payload
        source_agent = action.details.get("source_agent", "")
        target_agent = action.details.get("target_agent", "")

        # Update LOCAL state first (no read from guild_state, avoids race condition)
        guild_builder = self._get_local_state()
        routes = guild_builder.get("routes", [])

        # Find and remove matching routes
        removed_count = 0
        new_routes = []
        for route in routes:
            # Check if this route matches the source and target
            route_source = None
            if route.get("agent"):
                route_source = route["agent"].get("name") or route["agent"].get("id")
            elif route.get("agent_type"):
                route_source = route["agent_type"].split(".")[-1]

            route_target = None
            dest = route.get("destination", {})
            if dest and dest.get("topics"):
                topics = dest["topics"]
                route_target = topics[0] if isinstance(topics, list) else topics

            # Match route
            if (route_source and source_agent in str(route_source)) and \
               (route_target and target_agent in str(route_target)):
                removed_count += 1
            else:
                new_routes.append(route)

        if removed_count > 0:
            # Update local state and push to guild_state
            guild_builder["routes"] = new_routes
            self._save_local_state(ctx)

            ctx.send(
                TextFormat(
                    text=f"**Removed {removed_count} route(s)** from {source_agent} to {target_agent}",
                    title="Route Removed",
                )
            )
            # Request flowchart update
            ctx.send(FlowchartUpdateRequest(trigger="route_removed"))
        else:
            ctx.send(
                TextFormat(
                    text=f"**No matching routes found** from {source_agent} to {target_agent}",
                    title="Error",
                )
            )
