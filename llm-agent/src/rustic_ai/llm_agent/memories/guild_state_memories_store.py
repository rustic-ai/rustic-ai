from collections import deque
from typing import List, Literal

from pydantic import PrivateAttr

from rustic_ai.core.guild.agent import Agent, ProcessContext
from rustic_ai.core.guild.agent_ext.depends.llm.models import LLMMessage
from rustic_ai.core.guild.agent_ext.mixins.state_refresher import StateRefresherMixin
from rustic_ai.llm_agent.memories.memories_store import MemoriesStore


class GuildStateBackedMemoriesStore(MemoriesStore):

    memory_type: Literal["guild_state_backed"] = "guild_state_backed"

    _memory: deque = PrivateAttr()

    def remember(self, agent: Agent, ctx: ProcessContext, message: LLMMessage) -> None:
        # No-op: Guild-state backed memory does not store messages explicitly.
        pass

    def recall(self, agent: Agent, ctx: ProcessContext, context: List[LLMMessage]) -> List[LLMMessage]:
        if not isinstance(agent, StateRefresherMixin):
            return []
        self._memory = agent.get_guild_state().get("memories", [])
        return list(self._memory)
