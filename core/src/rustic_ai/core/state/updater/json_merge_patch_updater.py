import json_merge_patch

from rustic_ai.core.state.updater.state_updater import StateUpdater
from rustic_ai.core.utils import JsonDict


class JsonMergePatchUpdater(StateUpdater):
    """
    A class to apply a JSON merge patch to the state.
    """

    @staticmethod
    def apply_update(state: JsonDict, update: JsonDict) -> JsonDict:
        return json_merge_patch.merge(state, update)
