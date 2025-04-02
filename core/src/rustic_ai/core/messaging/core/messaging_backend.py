from abc import ABC, abstractmethod
from typing import Callable, Dict, List, Optional, Set

from rustic_ai.core.messaging.core.message import Message
from rustic_ai.core.utils.gemstone_id import GemstoneID


class MessagingBackend(ABC):
    """
    An abstract base class representing the storage interface for the message bus.
    """

    @abstractmethod
    def store_message(self, topic: str, message: Message) -> None:
        """
        Add a message to a topic.

        Args:
            topic (str): The topic to which the message belongs.
            message (Message): The message to be added.
        """
        pass  # pragma: no cover

    @abstractmethod
    def get_messages_for_topic(self, topic: str) -> List[Message]:
        """
        Retrieve all messages for a given topic.

        Args:
            topic (str): The topic to retrieve messages for.

        Returns:
            List[Message]: A list of messages for the given topic.
        """
        pass  # pragma: no cover

    @abstractmethod
    def get_messages_for_topic_since(self, topic: str, msg_id_since: int) -> List[Message]:
        """
        Retrieve all messages for a given topic since a specific message ID.

        Args:
            topic (str): The topic to retrieve messages for.
            msg_id_since (int): The message ID to start retrieving from.

        Returns:
            List[Message]: A list of messages for the given topic since the specified message ID.
        """
        pass  # pragma: no cover

    @abstractmethod
    def get_next_message_for_topic_since(self, topic: str, last_message_id: int) -> Optional[Message]:
        """
        Retrieve the next message for a given topic since a specific message ID.

        Args:
            topic (str): The topic to retrieve messages for.
            last_message_id (int): The message ID to start retrieving from.

        Returns:
            Message: A message for the given topic since the specified message ID.
        """
        pass  # pragma: no cover

    @abstractmethod
    def load_subscribers(self, namespace: str) -> Dict[str, Set[str]]:
        """
        Load all subscribers.

        Returns:
            Dict[str, Set[str]]: A dictionary mapping topics to sets of client IDs.
        """
        pass  # pragma: no cover

    def _get_timestamp_for_id(self, msg_id: int) -> float:
        """
        Helper method to retrieve the timestamp for a given message ID.

        Args:
            msg_id (int): The ID of the message.

        Returns:
            float: The timestamp of the message.
        """
        # Assuming you have a method to convert msg_id to timestamp
        if msg_id == 0 or msg_id is None:
            return 0
        id_instance = GemstoneID.from_int(msg_id)
        return id_instance.timestamp

    @abstractmethod
    def subscribe(self, topic: str, handler: Callable[[Message], None]) -> None:
        """
        Subscribe a handler to a specific topic.

        Args:
            topic (str): The topic to subscribe to.
            handler (Callable[[Message]): The callback handler for new messages.
        """
        pass  # pragma: no cover

    @abstractmethod
    def unsubscribe(self, topic: str) -> None:
        """
        Unsubscribe a handler from a specific topic.

        Args:
            topic (str): The topic to unsubscribe from.
        """
        pass  # pragma: no cover

    @abstractmethod
    def cleanup(self) -> None:
        """
        Clean up the storage implementation.
        """
        pass  # pragma: no cover

    def supports_subscription(self) -> bool:
        """
        Return whether the storage implementation supports subscription.

        Returns:
            bool: True if the storage implementation supports subscription, False otherwise.
        """
        return False  # pragma: no cover
