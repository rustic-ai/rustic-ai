import logging
from collections import deque
from typing import List

from pydantic import BaseModel

from rustic_ai.core.guild import agent
from rustic_ai.core.guild.agent import Agent, ProcessContext
from rustic_ai.core.guild.agent_ext.depends.llm import LLM
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    APIError,
    ChatCompletionError,
    ChatCompletionRequest,
    ResponseCodes,
    SystemMessage,
    UserMessage,
)
from rustic_ai.core.guild.dsl import AgentSpec, BaseAgentProps


class SimpleChatMessage(BaseModel):
    content: str


class SimpleChatResponse(BaseModel):
    content: str


class SimpleLLMAgentConf(BaseAgentProps):
    system_messages: List[str] = []
    chat_memory: int = 0


class SimpleLLMAgent(Agent[SimpleLLMAgentConf]):
    """
    This is a simple LLM agent, that will call and LLM and return the response.
    """

    def __init__(self, agent_spec: AgentSpec[SimpleLLMAgentConf]):
        super().__init__(agent_spec)
        conf = agent_spec.props

        self.memory: deque = deque(maxlen=conf.chat_memory)
        self.system_messages = [SystemMessage(content=message) for message in conf.system_messages]

    @agent.processor(SimpleChatMessage, depends_on=["llm"])
    def some_message_handler(self, ctx: ProcessContext[SimpleChatMessage], llm: LLM):
        """
        This is a simple LLM agent like that found in many agentic frameworks like AutoGen, Crew, etc.
        """
        data: SimpleChatMessage = ctx.payload

        message = UserMessage(content=data.content, name=ctx._origin_message.sender.id)

        self.memory.append(message)

        all_messages = self.system_messages + list(self.memory)

        try:
            response = llm.completion(ChatCompletionRequest(messages=all_messages))
            if response and response.choices and response.choices[0].message:
                ctx.send(SimpleChatResponse(content=response.choices[0].message.content))

        except APIError as err:  # pragma: no cover
            logging.error(f"Error in LLM completion: {err}")
            # Publish the error message
            ctx.send(
                ChatCompletionError(
                    status_code=ResponseCodes(err.status_code),
                    message=err.message,
                    model=llm.model,
                    request_messages=all_messages,
                )
            )
