from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Optional, Type

from rustic_ai.core.state.models import (
    StateFetchRequest,
    StateFetchResponse,
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
        updated_value = self.updaters[update_format].apply_update(value_at_path, update)
        return JsonUtils.update_at_path(state, path, updated_value) if path else updated_value

    @abstractmethod
    def get_state(self, request: StateFetchRequest) -> StateFetchResponse:
        """
        Get the state of the guild or an agent.

        Args:
            request: The request to get the state.

        Returns:
            The state of the guild or an agent.
        """
        pass

    @abstractmethod
    def update_state(self, request: StateUpdateRequest) -> StateUpdateResponse:
        """
        Update the state of the guild or an agent.

        Args:
            request: The request to set the state.

        Returns:
            The state of the guild or an agent.
        """
        pass

    @abstractmethod
    def init_from_state(self, state: JsonDict):
        """
        Initialize the state of the state manager.

        Args:
            state: The state to initialize.
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
