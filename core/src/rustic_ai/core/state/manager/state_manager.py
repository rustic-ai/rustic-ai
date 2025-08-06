from abc import ABC, abstractmethod
from enum import Enum
import logging
import time
from typing import Dict, Optional, Type, TypedDict, cast

from rustic_ai.core.state.models import (
    StateFetchRequest,
    StateFetchResponse,
    StateOwner,
    StateUpdateFormat,
    StateUpdateRequest,
    StateUpdateResponse,
)
from rustic_ai.core.state.updater import json_merge_patch_updater, json_patch_updater
from rustic_ai.core.state.updater.state_updater import StateUpdater
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.core.utils.json_utils import JsonDict, JsonUtils


class StateUpdaters(Enum):
    JSON_PATCH = json_patch_updater.JsonPatchUpdater
    JSON_MERGE_PATCH = json_merge_patch_updater.JsonMergePatchUpdater


class StateUpdateActions(Enum):
    AGENT_STATE_UPDATE = "agent_state_update"
    GUILD_STATE_UPDATE = "guild_state_update"


class StateDetails(TypedDict):
    """Type definition for state storage structure."""

    state: JsonDict
    version: int
    timestamp: int


class StateManager(ABC):

    updaters: Dict[StateUpdateFormat, Type[StateUpdater]] = {
        StateUpdateFormat.JSON_PATCH: StateUpdaters.JSON_PATCH.value,
        StateUpdateFormat.JSON_MERGE_PATCH: StateUpdaters.JSON_MERGE_PATCH.value,
    }

    def apply_state_update(
        self,
        update_format: StateUpdateFormat,
        state: Dict,
        path: Optional[str],
        update: Dict,
    ) -> Dict:
        """
        Apply the update to the state.

        Args:
            update_format: The format of the update.
            state: The state to update.
            update: The update to apply.

        Returns:
            The updated state.
        """
        value_at_path = JsonUtils.read_from_path(state, path) if path else state
        if value_at_path is None:
            # If the value at the path is None, we need to create the intermediate structure
            value_at_path = {}
        updated_value = self.updaters[update_format].apply_update(value_at_path, update)
        return JsonUtils.update_at_path(state, path, updated_value) if path else updated_value

    def __init__(self, **kwargs):
        """
        Base constructor that accepts keyword arguments.
        Subclasses should override this to handle their specific configuration.
        """
        pass

    @abstractmethod
    def _get_state_details(self, state_key: str) -> StateDetails:
        pass

    @abstractmethod
    def _set_state_details(self, state_key: str, state_details: StateDetails):
        pass

    @staticmethod
    def get_state_key(request: StateFetchRequest | StateUpdateRequest):
        if request.state_owner == StateOwner.GUILD:
            return request.guild_id
        else:
            return f"{request.guild_id}#{request.agent_id}"

    def get_state(self, request: StateFetchRequest) -> StateFetchResponse:
        """
        Get the state of the guild or an agent.

        Args:
            request: The request to get the state.

        Returns:
            The state of the guild or an agent.
        """
        state_details = self._get_state_details(self.get_state_key(request))
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
        """
        Update the state of the guild or an agent.

        Args:
            request: The request to set the state.

        Returns:
            The state of the guild or an agent.
        """
        state_key = self.get_state_key(request)
        state_details = self._get_state_details(state_key)

        old_state = state_details["state"]
        old_version = state_details["version"]

        logging.debug(f"Current state for {state_key}: {old_state}")
        state = self.apply_state_update(
            request.update_format,
            old_state,
            request.update_path,
            request.state_update,
        )
        logging.debug(f"Updated state for {state_key}: {state}")

        version = old_version + 1
        timestamp = time.time_ns() // 1000000

        self._set_state_details(
            state_key,
            {
                "state": state,
                "version": version,
                "timestamp": timestamp,
            },
        )

        return StateUpdateResponse(
            state_owner=request.state_owner,
            guild_id=request.guild_id,
            agent_id=request.agent_id,
            state=state,
            version=version,
            timestamp=timestamp,
        )

    @abstractmethod
    def load(self, state_data: JsonDict):
        """
        Load state data for the state manager.

        Args:
            state_data: state data to load into the state manager.
        """
        pass

    @classmethod
    def get_qualified_class_name(cls) -> str:
        """
        Returns the qualified name of the state manager.

        Returns:
            str: The qualified name of the state manager.
        """
        return get_qualified_class_name(cls)
