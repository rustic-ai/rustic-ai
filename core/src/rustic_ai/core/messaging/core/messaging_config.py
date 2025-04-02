import importlib
import inspect
import logging
from typing import Any, Dict

from pydantic import BaseModel

from rustic_ai.core.messaging.core.messaging_backend import MessagingBackend


class MessagingConfig(BaseModel):
    """
    A class to represent the configuration of a message bus.
    """

    backend_module: str
    backend_class: str
    backend_config: Dict[str, Any]

    def validate_config(self) -> None:
        """
        Validate the configuration.
        """
        mod = importlib.import_module(self.backend_module)
        backend_class = getattr(mod, self.backend_class)
        init_signature = inspect.signature(backend_class.__init__)
        for key in self.backend_config.keys():
            if key not in init_signature.parameters:
                raise ValueError(f"Invalid backend configuration key: {key}")

    def get_storage(self) -> MessagingBackend:
        """
        Initializes the storage for the Messaging based on the provided configuration.

        Returns:
            An instance of the Storage class.
        """
        try:
            mod = importlib.import_module(self.backend_module)
            backend_class = getattr(mod, self.backend_class)
            return backend_class(**self.backend_config)
        except Exception as e:  # pragma: no cover
            logging.error(f"Error initializing storage backend: {e}")
            raise ValueError(f"Error initializing storage backend: {e}")
