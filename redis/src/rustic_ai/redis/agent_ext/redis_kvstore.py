import json

import redis
from rustic_ai.core.guild.agent_ext.depends.dependency_resolver import (
    DependencyResolver,
)
from rustic_ai.core.guild.agent_ext.depends.kvstore.base import BaseKVStore


class RedisKVStore(BaseKVStore):
    def __init__(self, redis_client: redis.StrictRedis, guild_id: str, agent_id: str):
        self.store = redis_client
        self.guild_id = guild_id
        self.agent_id = agent_id

    def get(self, key: str):
        value = self.store.hget(f"{self.guild_id}_{self.agent_id}", key)
        return json.loads(value) if value else None

    def set(self, key: str, value):
        self.store.hset(f"{self.guild_id}_{self.agent_id}", mapping={key: json.dumps(value)})

    def delete(self, key: str):
        self.store.hdel(f"{self.guild_id}_{self.agent_id}", key)


class RedisKVStoreResolver(DependencyResolver[RedisKVStore]):
    def __init__(self, host: str, port: int) -> None:
        super().__init__()
        self.redis_client = redis.StrictRedis(host=host, port=port)

    def resolve(self, guild_id: str, agent_id: str) -> RedisKVStore:
        return RedisKVStore(redis_client=self.redis_client, guild_id=guild_id, agent_id=agent_id)
