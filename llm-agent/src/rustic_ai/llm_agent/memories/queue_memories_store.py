from collections import deque
from typing import List, Literal

from pydantic import PrivateAttr

from rustic_ai.core.guild.agent import Agent, ProcessContext
from rustic_ai.core.guild.agent_ext.depends.llm.models import LLMMessage
from rustic_ai.llm_agent.memories.memories_store import MemoriesStore


class QueueBasedMemoriesStore(MemoriesStore):

    memory_type: Literal["queue_based"] = "queue_based"
    memory_size: int = 36

    # Internal, non-serialized queue
    _memory_queue: deque = PrivateAttr()

    def model_post_init(self, __context):
        # Initialize the queue with the configured max size
        self._memory_queue = deque(maxlen=self.memory_size)

    def remember(self, agent: Agent, ctx: ProcessContext, message: LLMMessage) -> None:
        self._memory_queue.append(message)

    def recall(self, agent: Agent, ctx: ProcessContext, context: List[LLMMessage]) -> List[LLMMessage]:
        # For simplicity, just return the entire queue as relevant memories
        return list(self._memory_queue)
