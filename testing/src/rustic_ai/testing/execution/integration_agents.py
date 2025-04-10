import logging
from typing import Dict, List

from pydantic import JsonValue

from rustic_ai.core.agents.testutils.probe_agent import PublishMixin
from rustic_ai.core.guild import agent
from rustic_ai.core.guild.agent import Agent, AgentMode, AgentType, ProcessContext
from rustic_ai.core.guild.dsl import AgentSpec
from rustic_ai.core.messaging.core import JsonDict
from rustic_ai.core.messaging.core.message import Message


class LocalTestAgent(Agent, PublishMixin):
    def __init__(self, agent_spec: AgentSpec):
        super().__init__(agent_spec=agent_spec, agent_type=AgentType.BOT, agent_mode=AgentMode.LOCAL)
        self.captured_messages: List[Message] = []

    @agent.processor(JsonDict)
    def collect_message(self, ctx: agent.ProcessContext[JsonDict]) -> None:
        self.captured_messages.append(ctx.message.model_copy(deep=True))

    def publish_initial_message(self):
        # Publish the initial message to trigger communication between remote agents
        self.publish_dict("default_topic", {"content": "Initiate Flow"})

    def clear_messages(self):
        self.captured_messages.clear()


class InitiatorProbeAgent(Agent):
    """
    An agent that initiates communication.
    """

    def __init__(self, agent_spec: AgentSpec) -> None:
        super().__init__(agent_spec=agent_spec, agent_type=AgentType.BOT, agent_mode=AgentMode.LOCAL)

    @agent.processor(JsonDict, lambda me, message: message.topics == "default_topic")
    def initiate_flow(self, ctx: ProcessContext[JsonDict]) -> None:
        payload = ctx.payload
        if payload["content"] == "Initiate Flow":
            ctx.send_dict({"content": "Hello Responder!"})


class ResponderProbeAgent(Agent):
    """
    An agent that responds to received messages.
    """

    def __init__(self, agent_spec: AgentSpec) -> None:
        super().__init__(agent_spec=agent_spec, agent_type=AgentType.BOT, agent_mode=AgentMode.LOCAL)

    @agent.processor(JsonDict, lambda me, message: message.topics == "default_topic")
    def ack_response(self, ctx: ProcessContext) -> None:
        """
        Handles incoming messages by responding to them.
        """
        payload = ctx.payload
        logging.info(f"Received message: {ctx.message}\n")
        if payload["content"] == "Hello Responder!":
            response_content: Dict[str, JsonValue] = {"content": "Acknowledged: " + str(ctx.message.id)}
            ctx.send_dict(response_content)
