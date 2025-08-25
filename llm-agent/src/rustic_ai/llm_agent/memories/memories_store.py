from abc import abstractmethod
from typing import List, Literal
from pydantic import BaseModel
from rustic_ai.core.guild.agent import Agent, ProcessContext
from rustic_ai.core.guild.agent_ext.depends.llm.models import LLMMessage


class MemoriesStore(BaseModel):
    memory_type: Literal["queue_based", "history_based", "state_backed"]

    @abstractmethod
    def remember(self, agent: Agent, ctx: ProcessContext, message: LLMMessage) -> None:
        """
        Store a memory message.
        Different implementations will handle memory storage differently.
        Episodic memory might be stored in a way that captures the context of the conversation,
        while semantic memory might focus on the meaning and relationships between concepts. And so on.
        In some cases, where the source of memory is external to the conversation, this method will not
        do anything, e.g., if the memory is derived from a document or an external knowledge base.

        Args:
            message (LLMMessage): The message to add to the memory.

        """
        pass

    def remember_many(self, agent: Agent, ctx: ProcessContext, messages: List[LLMMessage]) -> None:
        """
        Store multiple memory messages.
        """
        for message in messages:
            self.remember(agent, ctx, message)

    @abstractmethod
    def recall(self, agent: Agent, ctx: ProcessContext, context: List[LLMMessage]) -> List[LLMMessage]:
        """
        Retrieve relevant memory messages based on the context.
        Different implementations will determine relevance in different ways.

        Args:
            context (List[LLMMessage]): The context to use for recalling memories.

        Returns:
            List[LLMMessage]: Relevant messages from the memory.
        """
        pass
