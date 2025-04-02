from abc import ABC, abstractmethod

from rustic_ai.core.utils import JsonDict


class StateUpdater(ABC):
    @staticmethod
    @abstractmethod
    def apply_update(state: JsonDict, update: JsonDict) -> JsonDict:
        """
        Apply the update to the state.

        Args:
            update: The update to apply.

        Returns:
            The updated state.
        """
        pass
