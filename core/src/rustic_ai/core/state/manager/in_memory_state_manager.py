import logging
from typing import Dict, cast

from rustic_ai.core.state.manager.state_manager import StateDetails, StateManager
from rustic_ai.core.utils.json_utils import JsonDict


class InMemoryStateManager(StateManager):
    def __init__(self):
        # Type as Dict[str, StateDetails] for proper type checking
        self._state: Dict[str, StateDetails] = {}

    def _get_state_details(self, state_key: str) -> StateDetails:
        logging.debug(f"Complete state: {self._state}")
        return self._state.get(state_key, {"state": {}, "version": 0, "timestamp": 0})

    def _set_state_details(self, state_key: str, state_details: StateDetails):
        logging.debug(f"Complete state: {self._state}")
        self._state[state_key] = state_details

    def load(self, state_data: JsonDict):
        # Convert JsonDict to our typed structure if needed
        # For now, assume it's already in the correct format
        self._state = cast(Dict[str, StateDetails], state_data)
