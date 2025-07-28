from rustic_ai.core.guild import Agent, AgentMode, AgentSpec, AgentType, agent
from rustic_ai.core.guild.agent import ProcessContext
from rustic_ai.core.messaging import MessageConstants
from rustic_ai.core.messaging.core import JsonDict


class BasicWiringAgent(Agent):
    """An Agent that wires the received message out to the destination."""

    def __init__(self, agent_spec: AgentSpec) -> None:
        super().__init__(
            agent_spec=agent_spec,
            agent_type=AgentType.BOT,
            agent_mode=AgentMode.LOCAL,
        )
        self.handled_formats = [MessageConstants.RAW_JSON_FORMAT]

        # Route messages to default topic if no specific routing is defined instead of the topic original message was read from
        self._route_to_default_topic = True

    @agent.processor(JsonDict)
    def wire_message(self, ctx: ProcessContext[JsonDict]) -> None:
        """
        Receives a message and writes it back.

        Args:
            ctx (ProcessContext[JsonDict]): The context of the message being processed.
        """
        ctx.send_dict(
            ctx.payload,
            format=ctx.message.format,
        )
