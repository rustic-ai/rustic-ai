"""
EnvoyAgent for sending cross-guild messages.

The EnvoyAgent represents a 1-1 connection to another guild. Each EnvoyAgent
instance is configured with a specific target_guild and forwards all messages
it receives to that guild via ctx.forward_out().
"""

from typing import List

from pydantic import Field

from rustic_ai.core.guild import agent
from rustic_ai.core.guild.g2g.boundary_agent import BoundaryAgent, BoundaryAgentProps
from rustic_ai.core.guild.g2g.boundary_context import BoundaryContext
from rustic_ai.core.utils import JsonDict


class EnvoyAgentProps(BoundaryAgentProps):
    """
    Properties for EnvoyAgent.

    Each EnvoyAgent represents a 1-1 connection to a specific external guild.

    Attributes:
        target_guild: The ID of the guild this envoy forwards messages to. Required.
        formats_to_forward: List of message format strings to forward. Empty = forward all.
    """

    target_guild: str = Field(
        description="The ID of the guild this envoy forwards messages to.",
    )

    formats_to_forward: List[str] = Field(
        default_factory=list,
        description="List of message format strings to forward. Empty = forward all.",
    )


class EnvoyAgent(BoundaryAgent[EnvoyAgentProps]):
    """
    Envoy agent that forwards messages to a specific external guild.

    Each EnvoyAgent represents a 1-1 connection to another guild. The target guild
    is configured via EnvoyAgentProps.target_guild.

    Does NOT subscribe to shared inbox. Listens to internal topics and forwards
    all received messages to the configured target guild via ctx.forward_out().

    Optionally filter by message format using formats_to_forward property.
    """

    @property
    def subscribe_to_shared_inbox(self) -> bool:
        return False

    def _should_forward(self, msg) -> bool:
        """Check if message format matches the filter (empty list = forward all)."""
        if not self.config or not self.config.formats_to_forward:
            return True
        return msg.format in self.config.formats_to_forward

    @agent.processor(
        JsonDict,
        predicate=lambda self, msg: self._should_forward(msg),
    )
    def handle_outbound(self, ctx: BoundaryContext) -> None:
        """Forward message to the configured target guild."""
        target_guild = self.config.target_guild

        if not self.is_target_guild_allowed(target_guild):
            return

        ctx.forward_out(target_guild, ctx.message)
