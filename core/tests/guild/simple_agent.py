from typing import List

from rustic_ai.core.guild import Agent, AgentMode, AgentType, BaseAgentProps, agent
from rustic_ai.core.guild.dsl import AgentSpec
from rustic_ai.core.messaging.core import JsonDict
from rustic_ai.core.messaging.core.message import Message


class SimpleAgent(Agent):
    def __init__(
        self,
        agent_spec: AgentSpec,
    ):
        super().__init__(agent_spec=agent_spec, agent_type=AgentType.BOT, agent_mode=AgentMode.LOCAL)
        self.received_messages: List[Message] = []

    @agent.processor(JsonDict)
    def collect_message(self, ctx: agent.ProcessContext[JsonDict]) -> None:
        self.received_messages.append(ctx.message.model_copy(deep=True))


class SimpleAgentProps(BaseAgentProps):
    prop1: str
    prop2: int


class SimpleAgentWithProps(Agent[SimpleAgentProps]):
    def __init__(self, agent_spec: AgentSpec[SimpleAgentProps]):
        super().__init__(agent_spec=agent_spec, agent_type=AgentType.BOT, agent_mode=AgentMode.LOCAL)
        self.received_messages: List[Message] = []
        self._props = agent_spec.props

    @agent.processor(JsonDict)
    def collect_message(self, ctx: agent.ProcessContext[JsonDict]) -> None:
        self.received_messages.append(ctx.message.model_copy(deep=True))
