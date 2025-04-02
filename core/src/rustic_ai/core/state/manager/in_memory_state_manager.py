import time

from rustic_ai.core.state.manager.state_manager import StateManager
from rustic_ai.core.state.models import (
    StateFetchRequest,
    StateFetchResponse,
    StateOwner,
    StateUpdateRequest,
    StateUpdateResponse,
)
from rustic_ai.core.utils.json_utils import JsonDict, JsonUtils


class InMemoryStateManager(StateManager):
    def __init__(self):
        self._state = {}

    def get_state(self, request: StateFetchRequest) -> StateFetchResponse:
        if request.state_owner == StateOwner.GUILD:
            state_details = self._state.get(request.guild_id, {})
            state = state_details.get("state", {})
            version = state_details.get("version", 0)
            timestamp = state_details.get("timestamp", 0)

            response_data = JsonUtils.read_from_path(state, request.state_path) if request.state_path else state

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
        elif request.state_owner == StateOwner.AGENT:
            state_details = self._state.get(f"{request.guild_id}#{request.agent_id}", {})
            state = state_details.get("state", {})
            version = state_details.get("version", 0)
            timestamp = state_details.get("timestamp", 0)

            response_data = JsonUtils.read_from_path(state, request.state_path) if request.state_path else state

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
            state_details = self._state.get(request.guild_id, {})
            old_state = state_details.get("state", {})
            old_version = state_details.get("version", 0)

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

            return StateUpdateResponse(
                state_owner=request.state_owner,
                guild_id=request.guild_id,
                state=state,
                version=version,
                timestamp=timestamp,
            )
        elif request.state_owner == StateOwner.AGENT:
            state_details = self._state.get(f"{request.guild_id}#{request.agent_id}", {})
            old_state = state_details.get("state", {})
            old_version = state_details.get("version", 0)

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

            return StateUpdateResponse(
                state_owner=request.state_owner,
                guild_id=request.guild_id,
                agent_id=request.agent_id,
                state=state,
                version=version,
                timestamp=timestamp,
            )

    def init_from_state(self, state: JsonDict):
        self._state = state
