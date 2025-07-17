import logging
import time
from typing import Dict, TypedDict, cast

from rustic_ai.core.state.manager.state_manager import StateManager
from rustic_ai.core.state.models import (
    StateFetchRequest,
    StateFetchResponse,
    StateOwner,
    StateUpdateRequest,
    StateUpdateResponse,
)
from rustic_ai.core.utils.json_utils import JsonDict, JsonUtils


class StateDetails(TypedDict):
    """Type definition for state storage structure."""

    state: JsonDict
    version: int
    timestamp: int


class InMemoryStateManager(StateManager):
    def __init__(self):
        # Type as Dict[str, StateDetails] for proper type checking
        self._state: Dict[str, StateDetails] = {}

    def get_state(self, request: StateFetchRequest) -> StateFetchResponse:
        if request.state_owner == StateOwner.GUILD:
            logging.debug(f"Complete state: {self._state}")
            state_details = self._state.get(request.guild_id, {"state": {}, "version": 0, "timestamp": 0})
            state = state_details["state"]
            version = state_details["version"]
            timestamp = state_details["timestamp"]

            if request.state_path:
                path_value = JsonUtils.read_from_path(state, request.state_path)
                # Wrap single values in a dict to match StateFetchResponse.state type
                if path_value is None:
                    # If path doesn't exist, return empty dict instead of {"key": None}
                    response_data = cast(JsonDict, {})
                elif isinstance(path_value, dict):
                    response_data = cast(JsonDict, path_value)
                else:
                    # Create a properly typed dict for non-dict values
                    key = request.state_path.split(".")[-1]
                    response_data = cast(JsonDict, {key: path_value})
            else:
                response_data = state

            return StateFetchResponse(
                state_owner=request.state_owner,
                guild_id=request.guild_id,
                state=response_data,
                state_path=request.state_path,
                version=version,
                timestamp=timestamp,
                fetch_timestamp=time.time_ns() // 1000000,
                is_latest=True,
            )
        else:
            logging.debug(f"Complete state: {self._state}")
            state_details = self._state.get(
                f"{request.guild_id}#{request.agent_id}", {"state": {}, "version": 0, "timestamp": 0}
            )
            state = state_details["state"]
            version = state_details["version"]
            timestamp = state_details["timestamp"]

            if request.state_path:
                path_value = JsonUtils.read_from_path(state, request.state_path)
                # Wrap single values in a dict to match StateFetchResponse.state type
                if path_value is None:
                    # If path doesn't exist, return empty dict instead of {"key": None}
                    response_data = cast(JsonDict, {})
                elif isinstance(path_value, dict):
                    response_data = cast(JsonDict, path_value)
                else:
                    # Create a properly typed dict for non-dict values
                    key = request.state_path.split(".")[-1]
                    response_data = cast(JsonDict, {key: path_value})
            else:
                response_data = state

            return StateFetchResponse(
                state_owner=request.state_owner,
                guild_id=request.guild_id,
                agent_id=request.agent_id,
                state=response_data,
                state_path=request.state_path,
                version=version,
                timestamp=timestamp,
                fetch_timestamp=time.time_ns() // 1000000,
                is_latest=True,
            )

    def update_state(self, request: StateUpdateRequest) -> StateUpdateResponse:
        if request.state_owner == StateOwner.GUILD:
            logging.debug(f"Current state: {self._state}")
            state_details = self._state.get(request.guild_id, {"state": {}, "version": 0, "timestamp": 0})
            old_state = state_details["state"]
            old_version = state_details["version"]

            state = self.apply_state_update(
                request.update_format,
                old_state,
                request.update_path,
                request.state_update,
            )
            version = old_version + 1
            timestamp = time.time_ns() // 1000000

            self._state[request.guild_id] = {
                "state": state,
                "version": version,
                "timestamp": timestamp,
            }

            logging.debug(f"Updated state: {self._state}")

            return StateUpdateResponse(
                state_owner=request.state_owner,
                guild_id=request.guild_id,
                state=state,
                version=version,
                timestamp=timestamp,
            )
        else:
            logging.debug(f"Current state: {self._state}")
            state_details = self._state.get(
                f"{request.guild_id}#{request.agent_id}", {"state": {}, "version": 0, "timestamp": 0}
            )
            old_state = state_details["state"]
            old_version = state_details["version"]

            state = self.apply_state_update(
                request.update_format,
                old_state,
                request.update_path,
                request.state_update,
            )
            version = old_version + 1
            timestamp = time.time_ns() // 1000000

            self._state[f"{request.guild_id}#{request.agent_id}"] = {
                "state": state,
                "version": version,
                "timestamp": timestamp,
            }

            logging.debug(f"Updated state: {self._state}")

            return StateUpdateResponse(
                state_owner=request.state_owner,
                guild_id=request.guild_id,
                agent_id=request.agent_id,
                state=state,
                version=version,
                timestamp=timestamp,
            )

    def init_from_state(self, state: JsonDict):
        # Convert JsonDict to our typed structure if needed
        # For now, assume it's already in the correct format
        self._state = cast(Dict[str, StateDetails], state)
