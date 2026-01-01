"""
GatewayAgent for bidirectional cross-guild communication.

The GatewayAgent acts as a server that handles cross-guild messaging:
- Inbound: Receives requests from external guilds and forwards internally
- Outbound: Forwards responses back to the origin guild's inbox
- Returned: Handles responses from external guilds, routing back through the chain

The origin_guild_stack tracks the chain of guilds for multi-hop routing.
Each guild pushes its ID when forwarding out, and pops when routing back.
"""

from typing import List

from pydantic import Field

from rustic_ai.core.guild import agent
from rustic_ai.core.guild.dsl import GuildTopics
from rustic_ai.core.guild.g2g.boundary_agent import BoundaryAgent, BoundaryAgentProps
from rustic_ai.core.guild.g2g.boundary_context import BoundaryContext
from rustic_ai.core.messaging import ForwardHeader
from rustic_ai.core.utils import JsonDict


class GatewayAgentProps(BoundaryAgentProps):
    """
    Properties for GatewayAgent.

    GatewayAgent acts as a server accepting requests from external guilds
    and sending responses back to the origin guild.

    Attributes:
        input_formats: Message formats to accept as incoming requests. Empty = accept all.
        output_formats: Message formats to forward back as responses. Empty = forward all.
        returned_formats: Message formats to accept as returned responses (results from
            external guilds). Empty = accept all.
    """

    input_formats: List[str] = Field(
        default_factory=list,
        description="Message formats to accept as incoming requests. Empty = accept all.",
    )

    output_formats: List[str] = Field(
        default_factory=list,
        description="Message formats to forward back as responses. Empty = forward all.",
    )

    returned_formats: List[str] = Field(
        default_factory=list,
        description="Message formats to accept as returned responses. Empty = accept all.",
    )


class GatewayAgent(BoundaryAgent[GatewayAgentProps]):
    """
    Gateway agent for bidirectional cross-guild communication.

    GatewayAgent acts as a server handling request/response flows:
    - Inbound requests: Messages from external guilds are forwarded internally for processing
    - Outbound responses: Response messages are forwarded back to the previous guild in the chain
    - Returned responses: Results coming back are routed through the origin_guild_stack

    The origin_guild_stack tracks the chain of guilds for multi-hop routing:
    - When A -> B -> C: stack becomes ["A", "B"] at C
    - When C responds: pop "B", route to B's inbox
    - When B responds: pop "A", route to A's inbox
    - When reaching origin (empty stack): forward internally, clear stack

    For client-side outbound-only communication, use EnvoyAgent.
    """

    def __init__(self):
        # Route inbound messages to default topic since incoming cross-guild
        # messages don't have valid internal routing information
        self._route_to_default_topic = True

    @property
    def subscribe_to_shared_inbox(self) -> bool:
        return True

    def _is_from_shared_inbox(self, message) -> bool:
        """Check if message came from the shared guild inbox."""
        return message.topic_published_to and message.topic_published_to.startswith("guild_inbox:")

    def _has_origin_stack(self, message) -> bool:
        """Check if message has an origin guild stack."""
        return bool(message.origin_guild_stack)

    def _get_stack_top(self, message) -> str:
        """Get the top of the origin guild stack (most recent forwarder)."""
        return message.origin_guild_stack[-1] if message.origin_guild_stack else None

    def _is_incoming_request(self, msg) -> bool:
        """Check if message is an incoming request from an external guild.

        A request comes from an external guild - the top of stack != this guild.
        """
        if not self._has_origin_stack(msg):
            return False
        return self._get_stack_top(msg) != self.guild_id

    def _is_returned_response(self, msg) -> bool:
        """Check if message is a returned response (result from external guild).

        A returned response has this guild at the top of the stack - meaning
        this guild forwarded the request and is now receiving the response.
        """
        if not self._has_origin_stack(msg):
            return False
        return self._get_stack_top(msg) == self.guild_id

    def _should_accept_inbound_request(self, msg) -> bool:
        """Check if inbound request from external guild should be accepted."""
        if not self._is_from_shared_inbox(msg):
            return False
        if not self._is_incoming_request(msg):
            return False
        # Check allowed_source_guilds filter - use the immediate sender (stack top)
        source_guild = self._get_stack_top(msg)
        if not self.is_source_guild_allowed(source_guild):
            return False
        if not self.config.input_formats:
            return True  # Empty = accept all
        return msg.format in self.config.input_formats

    def _should_accept_returned_response(self, msg) -> bool:
        """Check if returned response should be accepted."""
        if not self._is_from_shared_inbox(msg):
            return False
        if not self._is_returned_response(msg):
            return False
        if not self.config.returned_formats:
            return True  # Empty = accept all
        return msg.format in self.config.returned_formats

    def _should_forward_outbound(self, msg) -> bool:
        """Check if outbound message should be forwarded back to previous guild.

        Only forwards responses to external requests - i.e., messages where
        there's a guild stack and this guild is NOT at the top (meaning the
        request came from elsewhere and needs a response sent back).
        """
        # Only forward messages from internal topics (not from shared inbox)
        if self._is_from_shared_inbox(msg):
            return False
        # Don't forward messages sent by this gateway (prevent loops)
        if msg.sender.id == self.id:
            return False
        # Must have origin stack to know where to send the response
        if not self._has_origin_stack(msg):
            return False
        # Only forward if this guild is NOT at the top of stack
        # (i.e., this is a response to an external request)
        if self._get_stack_top(msg) == self.guild_id:
            return False
        # Check output format filter
        if not self.config.output_formats:
            return True  # Empty = forward all
        return msg.format in self.config.output_formats

    @agent.processor(
        JsonDict,
        predicate=lambda self, msg: self._should_accept_inbound_request(msg),
    )
    def handle_inbound_request(self, ctx: BoundaryContext) -> None:
        """Receive request from external guild and forward internally.

        Preserves origin_guild_stack so we know the return path.
        """
        # Forward internally - routing determined by guild configuration
        # Stack is preserved automatically via normal message copying
        ctx.send_dict(ctx.payload, ctx.message.format, forwarding=True)

    @agent.processor(
        JsonDict,
        predicate=lambda self, msg: self._should_accept_returned_response(msg),
    )
    def handle_returned_response(self, ctx: BoundaryContext) -> None:
        """Receive returned response and route back through the chain.

        Pops this guild from the stack and forwards internally. This allows
        processors in this guild to see/transform the response before it
        continues back through the chain.

        If more guilds remain in the stack after popping, handle_outbound will
        pick up the internally-forwarded message and route it to the next guild.
        If stack becomes empty, the round-trip is complete.
        """
        # Pop this guild from the stack
        new_stack = list(ctx.message.origin_guild_stack)
        new_stack.pop()  # Remove this guild (we're the top)

        # Create forwarded message with updated stack, targeting default topic
        forwarded = ctx.message.model_copy(
            deep=True,
            update={
                "forward_header": ForwardHeader(
                    origin_message_id=ctx.message.id,
                    on_behalf_of=ctx.message.sender,
                ),
                "origin_guild_stack": new_stack,
                "topics": GuildTopics.DEFAULT_TOPICS,  # Target internal default topic
                "session_state": None,
            },
        )

        # Forward internally to default topic
        # This allows processors in this guild to see/transform the response
        # If stack is not empty, handle_outbound will pick it up and forward to next guild
        ctx._client.publish(forwarded)

    @agent.processor(
        JsonDict,
        predicate=lambda self, msg: self._should_forward_outbound(msg),
    )
    def handle_outbound(self, ctx: BoundaryContext) -> None:
        """Forward response back to the previous guild in the chain.
        
        Unlike forward_out (used by Envoys for outbound requests), this does NOT
        push the current guild onto the stack. The stack already contains the
        return path and we're simply routing the response back.
        """
        # Get the guild to forward to (top of stack)
        target_guild = self._get_stack_top(ctx.message)

        if not self.is_target_guild_allowed(target_guild):
            return

        # Create forwarded message WITHOUT modifying the stack
        # (forward_out would push this guild, but we don't want that for responses)
        forwarded = ctx.message.model_copy(
            deep=True,
            update={
                "forward_header": ForwardHeader(
                    origin_message_id=ctx.message.id,
                    on_behalf_of=ctx.message.sender,
                ),
                # Don't modify origin_guild_stack - keep it as-is
                "session_state": None,  # Never cross guild boundaries
            },
        )

        ctx._boundary_client.publish_to_guild_inbox(target_guild, forwarded)
