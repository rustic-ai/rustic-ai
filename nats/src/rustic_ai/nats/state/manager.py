"""NATS KV-backed state manager."""

import json
import re
from typing import Dict, cast

from rustic_ai.core.state.manager.state_manager import StateDetails, StateManager
from rustic_ai.core.utils import JsonDict
from rustic_ai.nats.messaging.connection_manager import (
    NATSBackendConfig,
    NATSConnectionManager,
)


def _sanitize_key(key: str) -> str:
    """Sanitize a state key for use as a NATS KV key.

    NATS KV keys support alphanumerics, dots, dashes, and underscores.
    The StateManager uses '#' as agent state separator, ':' in some IDs.
    """
    return re.sub(r"[^a-zA-Z0-9.\-_]", "_", key)


class NATSStateManager(StateManager):
    """
    NATS JetStream KV implementation of StateManager.

    Stores state in a single KV bucket ('managed-state') using sanitized
    state keys. Each entry is a JSON-serialized dict with 'state', 'version',
    and 'timestamp' fields — mirroring the Redis hash structure.

    Key format:
      - Guild state:  <guild_id>
      - Agent state:  <guild_id>#<agent_id>
      Both are sanitized to replace non-NATS-safe characters with '_'.
    """

    KV_BUCKET = "managed-state"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        config = NATSBackendConfig.model_validate(kwargs)
        self._connection_mgr = NATSConnectionManager(config)
        self._js = self._connection_mgr.get_js()
        self._run_async = self._connection_mgr.run_async
        self._kv = self._run_async(self._ensure_bucket_async())

    async def _ensure_bucket_async(self):
        import nats.js.api

        try:
            return await self._js.create_key_value(
                nats.js.api.KeyValueConfig(bucket=self.KV_BUCKET)
            )
        except Exception:
            # Bucket may already exist
            return await self._js.key_value(self.KV_BUCKET)

    def _get_state_details(self, state_key: str) -> StateDetails:
        nats_key = _sanitize_key(state_key)
        try:
            entry = self._run_async(self._kv.get(nats_key))
            data = json.loads(entry.value.decode("utf-8"))
            return {
                "state": data.get("state", {}),
                "version": data.get("version", 0),
                "timestamp": data.get("timestamp", 0),
            }
        except Exception:
            return {"state": {}, "version": 0, "timestamp": 0}

    def _set_state_details(self, state_key: str, state_details: StateDetails):
        nats_key = _sanitize_key(state_key)
        data = json.dumps(
            {
                "state": state_details["state"],
                "version": state_details["version"],
                "timestamp": state_details["timestamp"],
            }
        ).encode("utf-8")
        self._run_async(self._kv.put(nats_key, data))

    def load(self, state_data: JsonDict):
        data = cast(Dict[str, StateDetails], state_data)
        for key, state_details in data.items():
            self._set_state_details(key, state_details)
