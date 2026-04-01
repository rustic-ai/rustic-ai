"""
Flowchart Agent for the Guild Generator.

This agent generates VegaLite visualizations of the guild flow,
showing agents as nodes and routes as edges.
"""

import logging
from typing import Any, Dict, List, Optional

from pydantic import Field

from rustic_ai.core.guild.agent import Agent, ProcessContext, processor
from rustic_ai.core.guild.dsl import BaseAgentProps
from rustic_ai.core.ui_protocol.types import VegaLiteFormat
from rustic_ai.showcase.guild_generator.models import (
    ActionType,
    FlowchartUpdateRequest,
    GuildBuilderState,
    OrchestratorAction,
)


class FlowchartAgentProps(BaseAgentProps):
    """Properties for the FlowchartAgent."""

    default_width: int = Field(default=600)
    default_height: int = Field(default=400)


class FlowchartAgent(Agent[FlowchartAgentProps]):
    """
    Agent that generates VegaLite visualizations of the guild flow.

    This agent reads the guild_builder state and creates a visual
    representation of agents and their routing connections.
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
        return None

    def _build_flowchart_spec(self, guild_state: Optional[GuildBuilderState]) -> Dict[str, Any]:
        """
        Build a VegaLite specification for the flowchart.

        Creates a network diagram showing agents as nodes and routes as edges.
        Uses a force-directed layout approximation with manually positioned nodes.
        """
        # Default state with just UserProxyAgent
        agents = [{"id": "user_proxy", "name": "UserProxyAgent", "type": "system"}]
        routes = []

        if guild_state:
            # Add agents from guild state
            for i, agent_spec in enumerate(guild_state.agents):
                agents.append(
                    {
                        "id": agent_spec.get("id", f"agent_{i}"),
                        "name": agent_spec.get("name", f"Agent {i}"),
                        "type": agent_spec.get("class_name", "unknown").split(".")[-1],
                    }
                )

            # Add routes from guild state
            for route in guild_state.routes:
                source = None
                target = None

                # Determine source from route
                if route.get("agent"):
                    source = route["agent"].get("name") or route["agent"].get("id")
                elif route.get("agent_type"):
                    source = route["agent_type"].split(".")[-1]

                # Determine target from destination
                dest = route.get("destination", {})
                if dest and dest.get("topics"):
                    topics = dest["topics"]
                    if isinstance(topics, list):
                        target = topics[0] if topics else None
                    else:
                        target = topics

                if source and target:
                    routes.append(
                        {
                            "source": source,
                            "target": target,
                            "format": route.get("message_format", "").split(".")[-1],
                        }
                    )

        # Position agents in a circle
        num_agents = len(agents)
        import math

        for i, agent in enumerate(agents):
            angle = (2 * math.pi * i) / num_agents
            agent["x"] = 300 + 200 * math.cos(angle)
            agent["y"] = 200 + 150 * math.sin(angle)

        # Build edge data
        edge_data = self._build_edge_data(agents, routes)

        # Build layers - only include edges layer if there are edges
        layers = []

        # Edges layer (routes) - only add if there are edges to avoid Vega-Lite errors with empty data
        if edge_data:
            layers.append(
                {
                    "data": {"values": edge_data},
                    "mark": {"type": "rule", "strokeWidth": 2, "opacity": 0.6},
                    "encoding": {
                        "x": {"field": "x1", "type": "quantitative", "scale": {"domain": [0, 600]}},
                        "y": {"field": "y1", "type": "quantitative", "scale": {"domain": [0, 400]}},
                        "x2": {"field": "x2", "type": "quantitative"},
                        "y2": {"field": "y2", "type": "quantitative"},
                        "color": {"value": "#4a90d9"},
                    },
                }
            )

        # Nodes layer (agents)
        layers.append(
            {
                "data": {"values": agents},
                "mark": {"type": "circle", "size": 800, "stroke": "#333", "strokeWidth": 2},
                "encoding": {
                    "x": {
                        "field": "x",
                        "type": "quantitative",
                        "axis": None,
                        "scale": {"domain": [0, 600]},
                    },
                    "y": {
                        "field": "y",
                        "type": "quantitative",
                        "axis": None,
                        "scale": {"domain": [0, 400]},
                    },
                    "color": {
                        "field": "type",
                        "type": "nominal",
                        "scale": {
                            "domain": ["system", "LLMAgent", "SplitterAgent", "AggregatingAgent", "unknown"],
                            "range": ["#95a5a6", "#3498db", "#e74c3c", "#2ecc71", "#9b59b6"],
                        },
                        "legend": {"title": "Agent Type"},
                    },
                    "tooltip": [
                        {"field": "name", "type": "nominal", "title": "Agent"},
                        {"field": "type", "type": "nominal", "title": "Type"},
                        {"field": "id", "type": "nominal", "title": "ID"},
                    ],
                },
            }
        )

        # Labels layer
        layers.append(
            {
                "data": {"values": agents},
                "mark": {"type": "text", "dy": 30, "fontSize": 11, "fontWeight": "bold"},
                "encoding": {
                    "x": {"field": "x", "type": "quantitative", "scale": {"domain": [0, 600]}},
                    "y": {"field": "y", "type": "quantitative", "scale": {"domain": [0, 400]}},
                    "text": {"field": "name", "type": "nominal"},
                },
            }
        )

        # Build VegaLite spec with layered visualization
        spec = {
            "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
            "title": {
                "text": guild_state.name if guild_state else "Guild Flow",
                "subtitle": guild_state.description if guild_state else "Add agents and routes to build your guild",
            },
            "width": self.config.default_width,
            "height": self.config.default_height,
            "layer": layers,
            "config": {"view": {"stroke": None}},
        }

        return spec

    def _build_edge_data(
        self, agents: List[Dict[str, Any]], routes: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Build edge data for the routes."""
        edges = []
        agent_positions = {a["name"]: (a["x"], a["y"]) for a in agents}
        agent_positions.update({a["id"]: (a["x"], a["y"]) for a in agents})

        for route in routes:
            source = route["source"]
            target = route["target"]

            if source in agent_positions and target in agent_positions:
                x1, y1 = agent_positions[source]
                x2, y2 = agent_positions[target]
                edges.append(
                    {
                        "x1": x1,
                        "y1": y1,
                        "x2": x2,
                        "y2": y2,
                        "source": source,
                        "target": target,
                        "format": route.get("format", ""),
                    }
                )

        return edges

    @processor(FlowchartUpdateRequest)
    def update_flowchart(self, ctx: ProcessContext[FlowchartUpdateRequest]):
        """
        Update and send the flowchart visualization.
        """
        guild_state = self._extract_guild_state(ctx)
        spec = self._build_flowchart_spec(guild_state)

        # Send VegaLiteFormat which the UI can render directly
        flowchart = VegaLiteFormat(
            spec=spec,
            alt="Guild Flow Diagram - Visual representation of the guild's agent and routing structure",
        )

        ctx.send(flowchart)

    @processor(
        OrchestratorAction,
        predicate=lambda self, msg: msg.payload.get("action") == ActionType.SHOW_FLOW,
    )
    def show_flowchart(self, ctx: ProcessContext[OrchestratorAction]):
        """
        Show the current flowchart when requested by orchestrator.
        """
        guild_state = self._extract_guild_state(ctx)
        spec = self._build_flowchart_spec(guild_state)

        # Send VegaLiteFormat which the UI can render directly
        flowchart = VegaLiteFormat(
            spec=spec,
            alt="Guild Flow Diagram - Visual representation of the guild's agent and routing structure",
        )

        ctx.send(flowchart)
