from abc import ABC, abstractmethod
from typing import List


class Embeddings(ABC):
    """
    Interface for embedding models.
    """

    @abstractmethod
    def embed(self, text: List[str]) -> List[List[float]]:
        """
        Get the embeddings for the given text.
        """
        pass
