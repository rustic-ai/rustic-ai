from typing import List

from pydantic import BaseModel

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

    @agent.processor(JsonDict)
    def collect_message(self, ctx: agent.ProcessContext[JsonDict]) -> None:
        self.received_messages.append(ctx.message.model_copy(deep=True))


class ErrorMessage(BaseModel):
    error_message: str


class SimpleErrorAgent(Agent):
    def __init__(self):
        self.received_messages: List[Message] = []

    @agent.processor(JsonDict)
    def error_producer(self, ctx: agent.ProcessContext[JsonDict]) -> None:
        ctx.send_error(ErrorMessage(error_message="An error occurred"))


class DummyMessage(BaseModel):
    key1: str
    key2: int


class DummyResponseOne(BaseModel):
    key1: str
    key2: int
    key3: str


class DummyResponseTwo(BaseModel):
    key1: str
    key2: int
    value1: str


class MultiProcessAgent(Agent):
    @agent.processor(DummyMessage)
    def process_all_messages(self, ctx: agent.ProcessContext[DummyMessage]) -> None:
        payload = ctx.payload
        result = DummyResponseOne(key1=payload.key1, key2=payload.key2, key3="Agent One")
        ctx.send(result)

    @agent.processor(DummyMessage, predicate=lambda x, m: m.payload["key2"] > 10)
    def process_filtered_messages(self, ctx: agent.ProcessContext[DummyMessage]) -> None:
        payload = ctx.payload
        result = DummyResponseTwo(key1=payload.key1, key2=payload.key2, value1="Agent Two")
        ctx.send(result)


class AccountableAgent(Agent):

    @agent.processor(JsonDict)
    def custom_handler(self, ctx: agent.ProcessContext[JsonDict]) -> None:
        try:
            payload = DummyMessage.model_validate(ctx.payload)
            result = DummyResponseOne(key1=payload.key1, key2=payload.key2, key3="Agent One")
            ctx.send(result, reason="Identified payload as DummyMessage")
        except Exception:
            ctx.send_error(ErrorMessage(error_message="An error occurred"), reason="Cannot read payload")
