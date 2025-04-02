from abc import ABC, abstractmethod
from typing import Optional


class SecretProvider(ABC):

    @abstractmethod
    def get_secret(self, key: str) -> Optional[str]:
        pass
