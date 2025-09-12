from collections import deque
from typing import List, Literal

import jsonpatch
from pydantic import PrivateAttr

from rustic_ai.core.guild.agent import Agent, ProcessContext
from rustic_ai.core.guild.agent_ext.depends.llm.models import LLMMessage
from rustic_ai.core.guild.agent_ext.mixins.state_refresher import StateRefresherMixin
from rustic_ai.core.state.models import StateUpdateFormat
from rustic_ai.llm_agent.memories.memories_store import MemoriesStore


class StateBackedMemoriesStore(MemoriesStore):

    memory_type: Literal["state_backed"] = "state_backed"
    memory_size: int = 12

    _memory: deque = PrivateAttr()

    def remember(self, agent: Agent, ctx: ProcessContext, message: LLMMessage) -> None:
        if not isinstance(agent, StateRefresherMixin):
            return

        if not self._memory:
            self._memory = deque(maxlen=self.memory_size)
            state_memories = agent._state.get("memories", [])
            self._memory.extend(state_memories)

        original_memories = {"memories": list(self._memory)}
        self._memory.append(message.model_dump())

        new_memories = {"memories": list(self._memory)}

        update = jsonpatch.make_patch(original_memories, new_memories)

        agent.update_state(
            ctx,
            update_format=StateUpdateFormat.JSON_PATCH,
            update=update,
            update_path="/",
        )

    def recall(self, agent: Agent, ctx: ProcessContext, context: List[LLMMessage]) -> List[LLMMessage]:
        if not isinstance(agent, StateRefresherMixin):
            return []
        self._memory = agent.get_agent_state().get("memories", [])
        return list(self._memory)
