import time

from rustic_ai.core.guild import Agent, AgentMode, AgentSpec, AgentType, agent
from rustic_ai.core.guild.agent import ProcessContext
from rustic_ai.core.messaging import MessageConstants
from rustic_ai.core.messaging.core import JsonDict


class EchoAgent(Agent):
    """An Agent that echoes the received message back to the sender."""

    def __init__(self, agent_spec: AgentSpec) -> None:
        super().__init__(
            agent_spec=agent_spec,
            agent_type=AgentType.BOT,
            agent_mode=AgentMode.LOCAL,
        )
        self.handled_formats = [MessageConstants.RAW_JSON_FORMAT]

    @agent.processor(JsonDict)
    def echo_message(self, ctx: ProcessContext[JsonDict]) -> None:
        """
        Processes the received message and echoes it back. The method receives
        a message context, processes the incoming payload, and sends the same payload back
        while maintaining the original message format. It applies a minimal delay during
        processing.

        Args:
            ctx (ProcessContext[JsonDict]): The context of the message being processed. Contains the payload
                    to be echoed back and additional metadata about the message.
        """
        time.sleep(0.001)

        ctx.send_dict(
            ctx.payload,
            format=ctx.message.format,
        )
