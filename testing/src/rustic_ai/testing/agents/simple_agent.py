from typing import List

from rustic_ai.core.guild import Agent, BaseAgentProps, agent
from rustic_ai.core.messaging.core import JsonDict
from rustic_ai.core.messaging.core.message import Message


class SimpleAgent(Agent):
    def __init__(self):
        self.received_messages: List[Message] = []

    @agent.processor(JsonDict)
    def collect_message(self, ctx: agent.ProcessContext[JsonDict]) -> None:
        self.received_messages.append(ctx.message.model_copy(deep=True))


class SimpleAgentProps(BaseAgentProps):
    prop1: str
    prop2: int


class SimpleAgentWithProps(Agent[SimpleAgentProps]):
    def __init__(self):
        self.received_messages: List[Message] = []
        self._props = self.config

    @agent.processor(JsonDict)
    def collect_message(self, ctx: agent.ProcessContext[JsonDict]) -> None:
        self.received_messages.append(ctx.message.model_copy(deep=True))
