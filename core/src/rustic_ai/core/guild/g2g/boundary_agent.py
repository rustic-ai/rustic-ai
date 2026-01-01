from typing import Callable, List, Type, TypeVar

from pydantic import Field

from rustic_ai.core.guild.agent import Agent
from rustic_ai.core.guild.dsl import BaseAgentProps
from rustic_ai.core.guild.g2g.boundary_context import BoundaryContext
from rustic_ai.core.messaging import Message
from rustic_ai.core.messaging.core.message import MDT


class BoundaryAgentProps(BaseAgentProps):
    """
    Base properties for boundary agents.

    Attributes:
        allowed_source_guilds: List of guild IDs allowed to send messages to this guild.
                              Empty list means all guilds are allowed.
        allowed_target_guilds: List of guild IDs this agent can send messages to.
                              Empty list means all guilds are allowed.
    """

    allowed_source_guilds: List[str] = Field(
        default_factory=list,
        description="Guild IDs allowed to send messages. Empty = allow all.",
    )
    allowed_target_guilds: List[str] = Field(
        default_factory=list,
        description="Guild IDs this agent can send to. Empty = allow all.",
    )


# TypeVar for BoundaryAgent props, bounded to BoundaryAgentProps
BAPT = TypeVar("BAPT", bound=BoundaryAgentProps)


class BoundaryAgent(Agent[BAPT]):
    """
    Base class for agents that communicate across guild boundaries.

    BoundaryAgent provides the base class for cross-guild communication.
    Actual messaging operations are performed through BoundaryContext,
    which wraps ProcessContext and provides cross-guild send methods.

    Subclasses:
        - GatewayAgent: Receives messages from other guilds and routes them internally
        - EnvoyAgent: Sends messages to other guilds on behalf of local agents

    To receive messages from other guilds, override `subscribe_to_shared_inbox` to return True.
    This will subscribe the agent to `guild_inbox:{guild_id}` in the shared namespace.

    Usage:
        class MyGatewayAgent(BoundaryAgent):
            @property
            def subscribe_to_shared_inbox(self) -> bool:
                return True

            @processor(IncomingMessage)
            def handle_incoming(self, ctx: BoundaryContext):
                # Process message from another guild
                ...

        class MyEnvoyAgent(BoundaryAgent):
            @processor(OutboundRequest)
            def handle_outbound(self, ctx: BoundaryContext):
                # Use BoundaryContext for cross-guild sends
                ctx.forward_out(target_guild_id, message)
    """

    @property
    def subscribe_to_shared_inbox(self) -> bool:
        """
        Whether to subscribe to this guild's inbox in the shared namespace.

        Override this to return True in Gateway agents that need to receive
        messages from other guilds. The agent will be subscribed to
        `guild_inbox:{guild_id}` in the organization namespace.

        Returns:
            True to subscribe to shared inbox, False otherwise.
        """
        return False

    def is_source_guild_allowed(self, source_guild_id: str) -> bool:
        """
        Check if a source guild is allowed to send messages.

        Args:
            source_guild_id: The ID of the guild sending the message.

        Returns:
            True if the guild is allowed, False otherwise.
        """
        if self.config and hasattr(self.config, "allowed_source_guilds") and self.config.allowed_source_guilds:
            return source_guild_id in self.config.allowed_source_guilds
        return True  # If no restrictions, allow all

    def is_target_guild_allowed(self, target_guild_id: str) -> bool:
        """
        Check if a target guild is allowed to receive messages.

        Args:
            target_guild_id: The ID of the guild to send to.

        Returns:
            True if the guild is allowed, False otherwise.
        """
        if self.config and hasattr(self.config, "allowed_target_guilds") and self.config.allowed_target_guilds:
            return target_guild_id in self.config.allowed_target_guilds
        return True  # If no restrictions, allow all

    def _make_process_context(
        self,
        message: Message,
        method_name: str,
        payload_type: Type[MDT],
        on_send_fixtures: List[Callable],
        on_error_filters: List[Callable],
        outgoing_message_modifiers: List[Callable],
    ) -> BoundaryContext:
        """
        Creates a BoundaryContext for cross-guild messaging capabilities.

        Args:
            message (Message): The message to be processed.

        Returns:
            BoundaryContext: The boundary context with cross-guild send methods.
        """
        boundary_ctx = BoundaryContext(
            self,
            message,
            method_name,
            payload_type,
            on_send_fixtures,
            on_error_filters,
            outgoing_message_modifiers,
        )

        return boundary_ctx
