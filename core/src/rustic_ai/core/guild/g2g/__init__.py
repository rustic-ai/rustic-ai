"""
Guild-to-Guild (G2G) Communication Module

This module provides infrastructure for cross-guild communication in Rustic AI.

Key Components:
    - BoundaryClient: Wrapper around Client that adds shared namespace operations
    - BoundaryAgent: Base class for agents that communicate across guild boundaries
    - BoundaryContext: Context wrapper for boundary agent message processing
    - GuildStackEntry: Tracks guild chain for multi-hop routing with saga support
    - SAGA_STATE_PREFIX: Key prefix for storing saga session state in guild_state

Architecture:
    Guilds communicate through a shared namespace (organization_id). Each guild
    has an inbox topic in the shared namespace: `guild_inbox:{guild_id}`.

    - Gateway agents subscribe to their guild's inbox and route incoming messages
    - Envoy agents send messages to other guilds' inboxes
    - Session state is automatically preserved across boundaries via saga pattern
      using StateRefresherMixin to persist state to the guild's StateManager

Example:
    class MyGatewayAgent(BoundaryAgent[BoundaryAgentProps]):
        def __init__(self):
            super().__init__()
            self.subscribe_to_guild_inbox()  # Subscribe to shared namespace inbox

        @processor(CrossGuildRequest)
        def handle_incoming(self, ctx: ProcessContext[CrossGuildRequest]):
            # Process incoming cross-guild message
            ctx.send(response, topics=["internal_topic"])
"""

from rustic_ai.core.guild.g2g.boundary_agent import BoundaryAgent, BoundaryAgentProps
from rustic_ai.core.guild.g2g.boundary_context import (
    SAGA_STATE_PREFIX,
    BoundaryContext,
    get_saga_state_key,
)
from rustic_ai.core.guild.g2g.envoy_agent import EnvoyAgent, EnvoyAgentProps
from rustic_ai.core.guild.g2g.gateway_agent import GatewayAgent, GatewayAgentProps
from rustic_ai.core.messaging import GuildStackEntry

__all__ = [
    "BoundaryAgent",
    "BoundaryAgentProps",
    "BoundaryContext",
    "EnvoyAgent",
    "EnvoyAgentProps",
    "GatewayAgent",
    "GatewayAgentProps",
    "GuildStackEntry",
    "SAGA_STATE_PREFIX",
    "get_saga_state_key",
]
