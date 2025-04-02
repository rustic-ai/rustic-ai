from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Callable, Optional, TypeVar

from rustic_ai.core.messaging.core.message import Message
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name

if TYPE_CHECKING:
    from .messaging_interface import MessagingInterface  # pragma: no cover

ClientType = TypeVar("ClientType", bound="Client", covariant=True)


class Client(ABC):
    """
    Abstract base class for a client.
    """

    def __init__(self, id: str, name: str, message_handler: Callable[[Message], None]):
        """
        Initialize the client with a unique ID and a name.
        """
        self._id = id
        self._name = name
        self._message_handler = message_handler
        self._messaging: Optional["MessagingInterface"] = None

    @property
    def id(self) -> str:
        """
        Return the unique ID of the client.
        """
        return self._id

    @property
    def name(self) -> str:
        """
        Return the name of the client.
        """
        return self._name  # pragma: no cover

    def connect(self, messaging: "MessagingInterface") -> None:
        """
        Set the message bus for the client.
        """
        if self._messaging is not None and self._messaging != messaging:
            raise RuntimeError("Message bus already set for this client")  # pragma: no cover
        if self._messaging is None:
            self._messaging = messaging

    def disconnect(self) -> None:
        """
        Unset the message bus for the client.
        """
        if self._messaging is None:
            raise RuntimeError("Message bus not set for this client")  # pragma: no cover
        self._messaging = None

    def publish(self, message: Message) -> None:
        """
        Publish a message to the message bus.

        Args:
            message: The message to publish.
        """
        if self._messaging is None:
            raise RuntimeError("Message bus not set for this client")  # pragma: no cover
        self._messaging.publish(self, message)

    @abstractmethod
    def notify_new_message(self, message: Message) -> None:
        """
        Notify the client of a new message.

        Args:
            message: The new message.
        """
        pass  # pragma: no cover

    @classmethod
    def get_qualified_class_name(cls) -> str:
        """
        Return the qualified name of the client class.
        """
        return get_qualified_class_name(cls)
