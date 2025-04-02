from typing import Any

from rustic_ai.core.guild.agent_ext.depends import DependencyResolver
from rustic_ai.core.guild.agent_ext.depends.kvstore import BaseKVStore


class InMemoryKVStore(BaseKVStore):
    """
    A simple in-memory key-value store.
    """

    def __init__(self):
        self.store = {}

    def get(self, key: str) -> Any:
        return self.store.get(key)

    def set(self, key: str, value: Any):
        self.store[key] = value

    def delete(self, key: str):
        del self.store[key]


class InMemoryKVStoreResolver(DependencyResolver[InMemoryKVStore]):

    def __init__(self) -> None:
        super().__init__()

    def resolve(self, guild_id: str, agent_id: str) -> InMemoryKVStore:
        return InMemoryKVStore()
