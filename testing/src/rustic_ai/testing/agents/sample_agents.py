from typing import Generic, TypeVar

from pydantic import BaseModel, Field

from rustic_ai.core.guild import Agent, AgentMode, AgentSpec, AgentType, agent
from rustic_ai.core.guild.dsl import BaseAgentProps

T = TypeVar("T")


class DemoAgentProps(BaseAgentProps):
    prop1: str = Field(default="default_value")
    prop2: int = Field(default=1)


class SimpleClass:
    pass


class GenericClass(Generic[T]):
    pass


class MessageDataType(BaseModel):
    data: str


class DemoAgentSimple(Agent):
    def __init__(self, agent_spec: AgentSpec):
        super().__init__(agent_spec=agent_spec, agent_type=AgentType.BOT, agent_mode=AgentMode.LOCAL)

    @agent.processor(MessageDataType)
    def handle_message(self, ctx: agent.ProcessContext[MessageDataType]):
        print(f"Received message: {ctx.payload.data}")


class DemoAgentGeneric(Agent[DemoAgentProps]):
    def __init__(self, agent_spec: AgentSpec[DemoAgentProps]):
        super().__init__(agent_spec=agent_spec, agent_type=AgentType.BOT, agent_mode=AgentMode.LOCAL)

    @agent.processor(MessageDataType)
    def handle_message(self, ctx: agent.ProcessContext[MessageDataType]):
        print(f"Received message: {ctx.payload.data}")


class DemoAgentGenericWithoutTypedSpec(Agent[DemoAgentProps]):
    def __init__(self, agent_spec: AgentSpec):
        super().__init__(agent_spec=agent_spec, agent_type=AgentType.BOT, agent_mode=AgentMode.LOCAL)

    @agent.processor(MessageDataType)
    def handle_message(self, ctx: agent.ProcessContext[MessageDataType]):
        print(f"Received message: {ctx.payload.data}")


class DemoAgentGenericWithoutTypedParams(Agent[DemoAgentProps]):
    def __init__(self, agent_spec):
        super().__init__(agent_spec=agent_spec, agent_type=AgentType.BOT, agent_mode=AgentMode.LOCAL)

    @agent.processor(MessageDataType)
    def handle_message(self, ctx: agent.ProcessContext[MessageDataType]):
        print(f"Received message: {ctx.payload.data}")


class DemoAgentWithMissingGenericAnnotation(Agent):
    def __init__(self, agent_spec: AgentSpec[DemoAgentProps]):
        super().__init__(agent_spec=agent_spec, agent_type=AgentType.BOT, agent_mode=AgentMode.LOCAL)

    @agent.processor(MessageDataType)
    def handle_message(self, ctx: agent.ProcessContext[MessageDataType]):
        print(f"Received message: {ctx.payload.data}")
