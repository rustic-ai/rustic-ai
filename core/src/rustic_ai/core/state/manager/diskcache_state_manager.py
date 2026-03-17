import json
from typing import Dict, cast

import diskcache

from rustic_ai.core.state.manager.state_manager import StateDetails, StateManager
from rustic_ai.core.utils.json_utils import JsonDict


class DiskCacheStateManager(StateManager):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        cache_dir = kwargs.get("cache_dir")
        if not cache_dir:
            raise ValueError("DiskCacheStateManager requires 'cache_dir' in config.")
        self._cache = diskcache.Cache(directory=cache_dir)

    def _get_state_details(self, state_key: str) -> StateDetails:
        raw = self._cache.get(state_key)
        if raw is None:
            return {"state": {}, "version": 0, "timestamp": 0}
        data = json.loads(raw)
        return {
            "state": data.get("state", {}),
            "version": int(data.get("version", 0)),
            "timestamp": int(data.get("timestamp", 0)),
        }

    def _set_state_details(self, state_key: str, state_details: StateDetails):
        self._cache.set(
            state_key,
            json.dumps(
                {
                    "state": state_details["state"],
                    "version": state_details["version"],
                    "timestamp": state_details["timestamp"],
                }
            ),
        )

    def load(self, state_data: JsonDict):
        data = cast(Dict[str, StateDetails], state_data)
        for key, details in data.items():
            self._set_state_details(key, details)
