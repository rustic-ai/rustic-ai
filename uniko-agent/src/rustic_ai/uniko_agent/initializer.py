"""Initialize memory workflow identity before expression-based routing."""

from rustic_ai.core.agents.commons.message_formats import ErrorMessage
from rustic_ai.core.guild import Agent, agent
from rustic_ai.core.guild.agent import ProcessContext
from rustic_ai.core.guild.agent_ext.depends.llm.models import ChatCompletionRequest


class MemoryRequestInitializerAgent(Agent):
    """Carry an exact request ID and User Proxy identity in existing context."""

    @agent.processor(ChatCompletionRequest)
    def initialize_request(self, ctx: ProcessContext[ChatCompletionRequest]) -> None:
        sender_id = ctx.message.sender.id
        request_id = ctx.message.id
        if (
            not isinstance(sender_id, str)
            or not sender_id.startswith("upa-")
            or not sender_id[4:].strip()
            or type(request_id) is not int
            or not 0 <= request_id < 2**64
        ):
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="memory_request_identity_unavailable",
                    error_message="The request could not be initialized. Please send it again.",
                )
            )
            return
        ctx.update_context({"request_id": str(request_id), "request_user": sender_id})
        # Preserve attachment metadata carried by the transport payload as well
        # as the typed request; FileUrl's parsed model omits MediaLink fields.
        ctx.send_dict(ctx.message.payload, format=ctx.message.format)
