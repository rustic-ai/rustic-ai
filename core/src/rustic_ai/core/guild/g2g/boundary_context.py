from typing import Callable, List, Type

from rustic_ai.core.guild.agent import Agent, ProcessContext
from rustic_ai.core.messaging import ForwardHeader, Message
from rustic_ai.core.messaging.core.boundary_client import BoundaryClient
from rustic_ai.core.messaging.core.message import MDT
from rustic_ai.core.utils import JsonDict


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
        if not hasattr(agent, "_organization_id") or not agent._organization_id:
            raise ValueError("No organization_id configured. Ensure the ExecutionEngine has organization_id set.")

        # Create BoundaryClient for cross-guild operations
        self._boundary_client = BoundaryClient(self._client, agent._organization_id)

    def forward_out(self, target_guild_id: str, message: Message) -> None:
        """
        Forward a message to another guild's inbox in the shared namespace.

        This creates a forwarded copy of the message with appropriate forward headers.
        The origin_guild_stack tracks the chain of guilds for multi-hop routing.
        Each guild in the chain pushes its ID onto the stack.

        Args:
            target_guild_id: The ID of the guild to send the message to.
            message: The message to forward.
        """
        # Push current guild onto the stack - enables multi-hop routing
        # The stack tracks the return path: A -> B -> C becomes ["A", "B"]
        new_stack = list(message.origin_guild_stack)
        new_stack.append(self.agent.guild_id)

        forwarded = message.model_copy(
            deep=True,
            update={
                "forward_header": ForwardHeader(
                    origin_message_id=message.id,
                    on_behalf_of=message.sender,
                ),
                "origin_guild_stack": new_stack,
                "session_state": None,  # Never cross guild boundaries
            },
        )

        self._boundary_client.publish_to_guild_inbox(target_guild_id, forwarded)
