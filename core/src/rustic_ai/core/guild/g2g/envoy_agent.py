"""
EnvoyAgent for sending cross-guild messages.

The EnvoyAgent represents a 1-1 connection to another guild. Each EnvoyAgent
instance is configured with a specific target_guild and forwards all messages
it receives to that guild via ctx.forward_out().

Session state is automatically preserved across the cross-guild boundary using
the saga pattern. When a message with session_state is forwarded, the state is
saved to guild_state via StateRefresherMixin.update_guild_state() with a saga_id.
When the response returns, GatewayAgent restores the session_state from guild_state,
enabling continuations to resume with their original context.
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
        formats_to_forward: List of message format strings to forward. Required.
    """

    target_guild: str = Field(
        description="The ID of the guild this envoy forwards messages to.",
    )

    formats_to_forward: List[str] = Field(
        min_length=1,
        description="List of message format strings to forward. Required.",
    )


class EnvoyAgent(BoundaryAgent[EnvoyAgentProps]):
    """
    Envoy agent that forwards messages to a specific external guild.

    Each EnvoyAgent represents a 1-1 connection to another guild. The target guild
    is configured via EnvoyAgentProps.target_guild.

    Does NOT subscribe to shared inbox. Listens to internal topics and forwards
    all received messages to the configured target guild via ctx.forward_out().

    Session state is automatically preserved: if the incoming message has session_state,
    it is saved to guild_state before forwarding. When the response returns, GatewayAgent
    restores the session_state, enabling seamless continuation across guild boundaries.

    Filter by message format using formats_to_forward property.
    """

    @property
    def subscribe_to_shared_inbox(self) -> bool:
        return False

    def _should_forward(self, msg) -> bool:
        """Check if message format matches the filter."""
        if not self.config or not self.config.formats_to_forward:
            return False

        if "*" in self.config.formats_to_forward:
            return True

        return msg.format in self.config.formats_to_forward

    @agent.processor(
        JsonDict,
        predicate=lambda self, msg: self._should_forward(msg),
    )
    def handle_outbound(self, ctx: BoundaryContext) -> None:
        """Forward message to the configured target guild.

        If the message has session_state, it will be automatically preserved
        via the saga pattern: saved to guild state and restored when the response returns.
        """
        target_guild = self.config.target_guild

        # forward_out handles saga state persistence internally using ctx.get_context()
        ctx.forward_out(target_guild, ctx.message)
