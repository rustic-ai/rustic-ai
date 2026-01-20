from typing import Callable, List, Optional, Type
import uuid

from rustic_ai.core.guild.agent import Agent, ProcessContext
from rustic_ai.core.messaging import ForwardHeader, GuildStackEntry, Message
from rustic_ai.core.messaging.core.boundary_client import BoundaryClient
from rustic_ai.core.messaging.core.message import MDT
from rustic_ai.core.state.models import StateUpdateFormat
from rustic_ai.core.utils import JsonDict

# Key prefix for storing saga session state in guild state
# Saga state is stored in the guild's shared state under this prefix
SAGA_STATE_PREFIX = "g2g_saga"


def get_saga_state_key(saga_id: str) -> str:
    """
    Create a key for saga state lookup within guild state.

    Args:
        saga_id: Unique saga identifier

    Returns:
        Key to use in guild state dict, e.g., "g2g_saga.abc123"
    """
    return f"{SAGA_STATE_PREFIX}.{saga_id}"


class BoundaryContext(ProcessContext[MDT]):
    """
    Context wrapper for BoundaryAgent processors that adds cross-guild messaging capabilities.

    BoundaryContext extends ProcessContext and adds methods for sending messages
    across guild boundaries via the shared namespace.

    The BoundaryContext creates a BoundaryClient from the agent's client and organization_id
    to publish messages to other guilds' inboxes in the shared (organization) namespace.
    """

    def __init__(
        self,
        agent: Agent,
        message: Message,
        method_name: str,
        payload_type: Type[MDT] = JsonDict,  # type: ignore
        on_send_fixtures: List[Callable] = [],
        on_error_fixtures: List[Callable] = [],
        outgoing_message_modifiers: List[Callable] = [],
    ):
        """
        Initialize the BoundaryContext.

        Args:
            agent: The agent processing the message.
            message: The message being processed.
            method_name: The name of the processor method.
            payload_type: The expected payload type.
            on_send_fixtures: Fixtures to run on send.
            on_error_fixtures: Fixtures to run on error.
            outgoing_message_modifiers: Modifiers for outgoing messages.

        Raises:
            ValueError: If the agent doesn't have an organization_id configured.
        """
        super().__init__(
            agent,
            message,
            method_name,
            payload_type,
            on_send_fixtures,
            on_error_fixtures,
            outgoing_message_modifiers,
        )

        # Get organization_id from agent
        organization_id = agent.get_organization()

        # Create BoundaryClient for cross-guild operations
        self._boundary_client = BoundaryClient(self._client, organization_id)

    def forward_out(
        self,
        target_guild_id: str,
        message: Message,
    ) -> None:
        """
        Forward a message to another guild's inbox in the shared namespace.

        This creates a forwarded copy of the message with appropriate forward headers.
        The origin_guild_stack tracks the chain of guilds for multi-hop routing.
        Each guild in the chain pushes a GuildStackEntry with its ID (and optional saga_id).

        Session state is automatically preserved: if the current context has state
        (via get_context()), it is saved to guild state via StateRefresherMixin with
        a generated saga_id. When the response returns, GatewayAgent restores it.

        Args:
            target_guild_id: The ID of the guild to send the message to.
            message: The message to forward.
        """
        # Get session state from context (already captured from message.session_state)
        session_state = self.get_context()

        # Generate saga_id and save session_state if not empty
        saga_id: Optional[str] = None
        if session_state:
            saga_id = str(uuid.uuid4())
            state_key = get_saga_state_key(saga_id)
            # Use StateRefresherMixin.update_guild_state to persist saga state
            self.agent.update_guild_state(
                self,
                update_format=StateUpdateFormat.JSON_MERGE_PATCH,
                update={state_key: session_state},
            )

        # Push current guild onto the stack - enables multi-hop routing
        # The stack tracks the return path: A -> B -> C becomes [Entry(A), Entry(B)]
        # saga_id is recorded so GatewayAgent can restore session_state on response
        new_stack = list(message.origin_guild_stack)
        new_stack.append(GuildStackEntry(guild_id=self.agent.guild_id, saga_id=saga_id))

        forwarded = message.model_copy(
            deep=True,
            update={
                "forward_header": ForwardHeader(
                    origin_message_id=message.id,
                    on_behalf_of=message.sender,
                ),
                "origin_guild_stack": new_stack,
                "session_state": {},  # Clear session_state - never cross guild boundaries
            },
        )

        self._boundary_client.publish_to_guild_inbox(target_guild_id, forwarded)
