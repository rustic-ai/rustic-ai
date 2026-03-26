"""
Guild Generator - A meta-guild for building guilds interactively.

This module provides a guild that can generate other guilds. Users can:
1. Tag @Orchestrator to add agents, routes, and configure the guild
2. Send normal messages to test the guild flow
3. Export the final guild spec when satisfied
"""

from rustic_ai.showcase.guild_generator.models import (
    ActionType,
    AgentLookupRequest,
    AgentLookupResponse,
    AgentRegistryInfo,
    ExportRequest,
    ExportResponse,
    FlowchartUpdateRequest,
    GuildBuilderState,
    OrchestratorAction,
    RouteRequest,
    RouteResponse,
    TransformationSpec,
    TransformRequest,
    TransformResponse,
)

from rustic_ai.showcase.guild_generator.orchestrator import (
    OrchestratorAgent,
    OrchestratorAgentProps,
)

from rustic_ai.showcase.guild_generator.agent_registry import (
    AgentRegistryAgent,
    AgentRegistryAgentProps,
    AGENT_REGISTRY,
)

from rustic_ai.showcase.guild_generator.transformation_builder import (
    TransformationBuilderAgent,
    TransformationBuilderAgentProps,
)

from rustic_ai.showcase.guild_generator.route_builder import (
    RouteBuilderAgent,
    RouteBuilderAgentProps,
)

from rustic_ai.showcase.guild_generator.flowchart_agent import (
    FlowchartAgent,
    FlowchartAgentProps,
)

from rustic_ai.showcase.guild_generator.guild_export import (
    GuildExportAgent,
    GuildExportAgentProps,
)

from rustic_ai.showcase.guild_generator.state_manager import (
    StateManagerAgent,
    StateManagerAgentProps,
)

__all__ = [
    # Models
    "ActionType",
    "AgentLookupRequest",
    "AgentLookupResponse",
    "AgentRegistryInfo",
    "ExportRequest",
    "ExportResponse",
    "FlowchartUpdateRequest",
    "GuildBuilderState",
    "OrchestratorAction",
    "RouteRequest",
    "RouteResponse",
    "TransformationSpec",
    "TransformRequest",
    "TransformResponse",
    # Agents
    "OrchestratorAgent",
    "OrchestratorAgentProps",
    "AgentRegistryAgent",
    "AgentRegistryAgentProps",
    "AGENT_REGISTRY",
    "TransformationBuilderAgent",
    "TransformationBuilderAgentProps",
    "RouteBuilderAgent",
    "RouteBuilderAgentProps",
    "FlowchartAgent",
    "FlowchartAgentProps",
    "GuildExportAgent",
    "GuildExportAgentProps",
    "StateManagerAgent",
    "StateManagerAgentProps",
]
