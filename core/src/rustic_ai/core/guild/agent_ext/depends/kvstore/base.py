from abc import ABC, abstractmethod
from typing import Any


class BaseKVStore(ABC):
    """
    Abstract base class for key-value stores.
    """

    @abstractmethod
    def get(self, key: str) -> Any:
        """
        Get the value of a key.

        Args:
            key: The key to get the value of.

        Returns:
            The value of the key.
        """
        pass  # pragma: no cover

    @abstractmethod
    def set(self, key: str, value: Any) -> None:
        """
        Set the value of a key.

        Args:
            key: The key to set the value of.
            value: The value to set.
        """
        pass  # pragma: no cover

    @abstractmethod
    def delete(self, key: str) -> None:
        """
        Delete a key.

        Args:
            key: The key to delete.
        """
        pass  # pragma: no cover
