from abc import ABC, abstractmethod
from typing import List


class TextSplitter(ABC):
    """
    Interface for text splitters.
    """

    @abstractmethod
    def split(self, text: str) -> List[str]:
        """
        Split the given text into chunks.

        Args:
            text: The text to split.

        Returns:
            A list of text chunks.
        """
        pass
