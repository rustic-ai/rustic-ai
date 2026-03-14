"""NATS KV-backed agent key-value store."""

import json
import re

from rustic_ai.core.guild.agent_ext.depends.dependency_resolver import (
    DependencyResolver,
)
from rustic_ai.core.guild.agent_ext.depends.kvstore.base import BaseKVStore
from rustic_ai.nats.messaging.connection_manager import (
    NATSBackendConfig,
    NATSConnectionManager,
)


def _sanitize(name: str) -> str:
    """Replace characters not valid in NATS KV key tokens with underscores."""
    return re.sub(r"[^a-zA-Z0-9\-_]", "_", name)


class NATSKVStore(BaseKVStore):
    """Agent KV store backed by a NATS JetStream KV bucket.

    All agents share a single bucket ('agent-kvstore').  Each agent's
    entries are prefixed with '{org_id}.{guild_id}.{agent_id}.' so they
    are logically isolated, mirroring how Redis scopes by hash key.
    """

    KV_BUCKET = "agent-kvstore"

    def __init__(self, kv, run_async, org_id: str, guild_id: str, agent_id: str):
        self._kv = kv
        self._run_async = run_async
        self._prefix = f"{_sanitize(org_id)}.{_sanitize(guild_id)}.{_sanitize(agent_id)}"

    def _full_key(self, key: str) -> str:
        return f"{self._prefix}.{_sanitize(key)}"

    def get(self, key: str):
        try:
            entry = self._run_async(self._kv.get(self._full_key(key)))
            return json.loads(entry.value.decode("utf-8"))
        except Exception:
            return None

    def set(self, key: str, value) -> None:
        self._run_async(self._kv.put(self._full_key(key), json.dumps(value).encode("utf-8")))

    def delete(self, key: str) -> None:
        try:
            self._run_async(self._kv.delete(self._full_key(key)))
        except Exception:
            pass


class NATSKVStoreResolver(DependencyResolver[NATSKVStore]):
    """Resolves NATSKVStore instances for agents, sharing a single NATS connection."""

    def __init__(self, **kwargs) -> None:
        super().__init__()
        config = NATSBackendConfig.model_validate(kwargs)
        self._connection_mgr = NATSConnectionManager(config)
        self._js = self._connection_mgr.get_js()
        self._run_async = self._connection_mgr.run_async
        self._kv = self._run_async(self._ensure_bucket_async())

    async def _ensure_bucket_async(self):
        import nats.js.api

        try:
            return await self._js.create_key_value(
                nats.js.api.KeyValueConfig(bucket=NATSKVStore.KV_BUCKET)
            )
        except Exception:
            return await self._js.key_value(NATSKVStore.KV_BUCKET)

    def resolve(self, org_id: str, guild_id: str, agent_id: str) -> NATSKVStore:
        return NATSKVStore(
            kv=self._kv,
            run_async=self._run_async,
            org_id=org_id,
            guild_id=guild_id,
            agent_id=agent_id,
        )
