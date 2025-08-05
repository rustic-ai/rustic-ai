import json
from typing import Dict, cast

from rustic_ai.core.state.manager.state_manager import StateDetails, StateManager
from rustic_ai.core.utils import JsonDict
from rustic_ai.redis.messaging import RedisBackendConfig
from rustic_ai.redis.messaging.connection_manager import RedisConnectionManager


class RedisStateManager(StateManager):
    """
    Redis implementation of the StateManager interface.

    Stores state data in Redis using hashes with the following fields:
    - state: The actual state data (serialized JSON)
    - version: The version number
    - timestamp: The timestamp in milliseconds

    Keys are structured as:
    - For guild state: managed_state:guild:{guild_id}
    - For agent state: managed_state:agent:{guild_id}:{agent_id}
    """

    REDIS_KEY_PREFIX = "managed_state"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Initialize connection manager
        redis_config = RedisBackendConfig.model_validate(kwargs)
        connection_mgr = RedisConnectionManager(redis_config)
        # Get client from connection manager
        self.client = connection_mgr.get_client()

    def _get_state_details(self, state_key: str) -> StateDetails:
        # Get state details from Redis
        state_data = self.client.hgetall(f"{self.REDIS_KEY_PREFIX}:{state_key}")

        # If no data found, return empty state
        if not state_data:
            return {"state": {}, "version": 0, "timestamp": 0}

        # Convert to StateDetails
        return {
            "state": json.loads(state_data.get("state") or "{}"),
            "version": int(state_data.get("version", 0)),
            "timestamp": int(state_data.get("timestamp")),
        }

    def _set_state_details(self, state_key: str, state_details: StateDetails):
        self.client.hset(
            f"{self.REDIS_KEY_PREFIX}:{state_key}",
            mapping={
                "state": json.dumps(state_details["state"]),
                "version": str(state_details["version"]),
                "timestamp": str(state_details["timestamp"]),
            },
        )

    def load(self, state_data: JsonDict):
        data = cast(Dict[str, StateDetails], state_data)
        for key, state_details in data.items():
            self._set_state_details(key, state_details)
