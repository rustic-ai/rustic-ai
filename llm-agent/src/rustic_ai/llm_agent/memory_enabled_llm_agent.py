from abc import abstractmethod
from typing import List

from rustic_ai.core.guild.agent import Agent, ProcessContext, processor
from rustic_ai.core.guild.agent_ext.depends.llm.llm import LLM
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    LLMMessage,
    SystemMessage,
)
from rustic_ai.llm_agent.basic_llm_agent import BasicLLMAgentConfig, LLMInvocationMixin
from rustic_ai.llm_agent.llm_agent_conf import LLMAgentConfig
from rustic_ai.llm_agent.llm_agent_helper import LLMAgentHelper
from rustic_ai.llm_agent.llm_agent_utils import LLMAgentUtils
from rustic_ai.llm_agent.memories.memories_store import MemoriesStore


class MemoryEnabledAgentConfig(BasicLLMAgentConfig):
    """
    Configuration for memory-enabled LLM agents.
    """

    memory_stores: List[MemoriesStore]

    def get_llm_params(self) -> dict:
        return self.model_dump(
            exclude_none=True,
            exclude={"memory_stores"},
        )


class MemoryEnabledLLMInvocationMixin:
    """
    Mixin class to add LLM invocation capabilities to an agent.
    """

    def get_prefix_messages(self, ctx: ProcessContext[ChatCompletionRequest], llm: LLM) -> List[LLMMessage]:
        prefix_messages = [SystemMessage(role="system", content=self.config.system_prompt)]

        # Collect memories from each configured store using the standard recall API
        for store in self.config.memory_stores:
            try:
                memories = store.recall(self, ctx, ctx.payload.messages)
            except Exception:
                memories = []
            if memories:
                prefix_messages.extend(memories)

        return prefix_messages

    def record_memory(
        self, ctx: ProcessContext[ChatCompletionRequest], llm: LLM, response: ChatCompletionResponse
    ) -> None:
        # If the response is valid, store the user messages and LLM response in memory.
        if (
            isinstance(self.config, MemoryEnabledAgentConfig)
            and response
            and isinstance(response, ChatCompletionResponse)
        ):
            user_messages = ctx.payload.messages
            for store in self.config.memory_stores:
                store.remember_many(self, ctx, user_messages)

            llm_response = response.choices[0].message

            for store in self.config.memory_stores:
                store.remember(self, ctx, llm_response)

    @processor(
        ChatCompletionRequest,
        predicate=lambda self, msg: LLMAgentUtils.has_no_attachments(msg),
        depends_on=["llm"],
    )
    def invoke_llm(self, ctx: ProcessContext[ChatCompletionRequest], llm: LLM):
        """
        Invoke the LLM with the given context. All the LLM configuration parameters are passed along.
        The System prompt is set in prefix messages.
        """

        prefix_messages = self.get_prefix_messages(ctx, llm)
        response = LLMAgentHelper.invoke_llm_and_handle_response(
            self.name,
            prefix_messages,
            self.config,
            ctx.payload,
            llm,
            ctx,
        )
        self.record_memory(ctx, llm, response)


class MemoryEnabledLLMAgent(Agent[MemoryEnabledAgentConfig], MemoryEnabledLLMInvocationMixin):
    """Memory-enabled LLM agent that uses memory stores to enhance its capabilities."""

    pass
