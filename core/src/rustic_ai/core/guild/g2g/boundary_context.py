from typing import List, Optional

from rustic_ai.core.guild.agent import (
    AgentTag,
    ProcessContext,
    ProcessEntry,
    ProcessStatus,
)
from rustic_ai.core.messaging import ForwardHeader, Message, Priority, RoutingSlip
from rustic_ai.core.messaging.core.boundary_client import BoundaryClient
from rustic_ai.core.utils import JsonDict


class BoundaryContext(ProcessContext):
    """
    Context wrapper for BoundaryAgent processors that adds cross-guild messaging capabilities.

    BoundaryContext wraps a standard ProcessContext and delegates all normal operations to it,
    while adding methods for sending messages across guild boundaries via the shared namespace.

    The BoundaryContext creates a BoundaryClient from the agent's client and organization_id
    to publish messages to other guilds' inboxes in the shared (organization) namespace.
    """

    def __init__(self, ctx: ProcessContext):
        """
        Initialize the BoundaryContext.

        Args:
            ctx: The underlying ProcessContext to wrap.

        Raises:
            ValueError: If the agent doesn't have an organization_id configured.
        """
        self._ctx = ctx

        # Get organization_id from agent
        agent = ctx.agent
        if not hasattr(agent, "_organization_id") or not agent._organization_id:
            raise ValueError("No organization_id configured. Ensure the ExecutionEngine has organization_id set.")

        # Create BoundaryClient for cross-guild operations
        self._boundary_client = BoundaryClient(ctx._client, agent._organization_id)

    def __getattr__(self, name):
        """Delegate attribute access to the wrapped ProcessContext."""
        return getattr(self._ctx, name)

    def forward_out(self, target_guild_id: str, message: Message) -> None:
        """
        Forward a message to another guild's inbox in the shared namespace.

        This creates a forwarded copy of the message with appropriate forward headers.

        Args:
            target_guild_id: The ID of the guild to send the message to.
            message: The message to forward.
        """
        return self._direct_send_out(
            priority=message.priority,
            target_guild_id=target_guild_id,
            payload=message.payload,
            format=message.format,
            in_response_to=message.in_response_to,
            recipient_list=message.recipient_list,
            ttl=message.ttl,
            forward_header=ForwardHeader(
                origin_message_id=message.id,
                on_behalf_of=message.sender,
            ),
            routing_slip=None,
            is_error_message=message.is_error_message,
            traceparent=message.traceparent,
            process_status=message.process_status,
            reason=(
                message.message_history[-1].reason[0]
                if message.message_history and message.message_history[-1].reason
                else None
            ),
        )

    def _direct_send_out(
        self,
        priority: Priority,
        target_guild_id: str,
        payload: JsonDict,
        format: str,
        in_response_to: Optional[int] = None,
        recipient_list: List[AgentTag] = [],
        ttl: Optional[int] = None,
        message_history: List[ProcessEntry] = [],
        forward_header: Optional[ForwardHeader] = None,
        routing_slip: Optional[RoutingSlip] = None,
        is_error_message: bool = False,
        traceparent: Optional[str] = None,
        session_state: Optional[JsonDict] = None,
        process_status: Optional[ProcessStatus] = None,
        reason: Optional[str] = None,
    ) -> None:
        """
        Send a message to another guild's inbox via the shared namespace.

        This method constructs a Message and publishes it to the target guild's
        inbox topic in the shared (organization) namespace using the BoundaryClient.

        Args:
            priority: Message priority.
            target_guild_id: The ID of the target guild.
            payload: The message payload.
            format: The message format identifier.
            in_response_to: ID of the message this is responding to.
            recipient_list: List of specific recipients.
            ttl: Time-to-live for the message.
            message_history: Processing history.
            forward_header: Forward header if forwarding.
            routing_slip: Routing instructions (typically None for cross-guild).
            is_error_message: Whether this is an error message.
            traceparent: Trace context for distributed tracing.
            session_state: Session state to include.
            process_status: Processing status.
            reason: Reason for sending.
        """
        msg_id = self._get_id(priority)
        origin_message = self._ctx._origin_message
        thread = origin_message.thread.copy()

        if not in_response_to:
            in_response_to = origin_message.id

        if not message_history:
            message_history = origin_message.message_history.copy()

        message_history.append(
            ProcessEntry(
                agent=self._ctx.agent.get_agent_tag(),
                processor=self._ctx.method_name,
                origin=origin_message.id,
                result=msg_id.to_int(),
                reason=[reason] if reason else None,
            )
        )

        if not traceparent:
            traceparent = origin_message.traceparent

        # Create the message for cross-guild delivery
        message = Message(
            id_obj=msg_id,
            topics=[f"guild_inbox:{target_guild_id}"],
            sender=self._ctx.agent.get_agent_tag(),
            payload=payload,
            format=format,
            in_response_to=in_response_to,
            recipient_list=recipient_list,
            thread=thread,
            ttl=ttl,
            message_history=message_history,
            forward_header=forward_header,
            routing_slip=routing_slip,
            is_error_message=is_error_message,
            traceparent=traceparent,
            session_state=session_state,
            process_status=process_status,
        )

        # Use BoundaryClient to publish to target guild's inbox
        self._boundary_client.publish_to_guild_inbox(target_guild_id, message)
