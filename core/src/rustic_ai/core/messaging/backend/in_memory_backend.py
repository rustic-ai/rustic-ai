import bisect
import random
from typing import Callable, Dict, List, Optional, Set

import shortuuid

from rustic_ai.core.messaging.core import Message
from rustic_ai.core.messaging.core.messaging_backend import MessagingBackend


class MemoryStore:
    _instance = None  # type: ignore
    _id = None  # type: ignore

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MemoryStore, cls).__new__(cls)
            cls._initialized = False
            cls._id = random.randint(0, 10)  # Helpful in debugging
            cls._instance_count = 0  # Helpful in debugging

        return cls._instance

    def __init__(self):
        if not self._initialized:
            self.topics: Dict[str, List[Message]] = {}
            self.subscribers: Dict[str, Set[str]] = {}
            self.callback_handlers: Dict[str, Dict[str, Callable[[Message], None]]] = {}
            self.is_initialized = True
            self._my_id = random.randint(0, 10)  # Helpful in debugging

    def store_message(self, topic: str, message: Message) -> None:
        message = message.model_copy(deep=True)
        if topic not in self.topics:
            self.topics[topic] = []
        bisect.insort_left(self.topics[topic], message, key=lambda msg: msg.timestamp)

    def get_messages_for_topic(self, topic: str) -> List[Message]:
        msgs = sorted(self.topics.get(topic, []), key=lambda msg: msg.id)
        return [msg.model_copy(deep=True) for msg in msgs]

    def get_messages_for_topic_since(self, topic: str, timestamp_since: float) -> List[Message]:
        topic_messages = [msg for msg in self.get_messages_for_topic(topic) if msg.timestamp > timestamp_since]
        return topic_messages

    def get_next_message_for_topic_since(self, topic: str, timestamp_since: float) -> Optional[Message]:
        topic_messages = self.get_messages_for_topic(topic)
        topic_messages = [msg for msg in topic_messages if msg.timestamp > timestamp_since]
        sorted_messages = sorted(topic_messages, key=lambda msg: msg.id)
        return sorted_messages[0].model_copy(deep=True) if sorted_messages else None

    def get_callback_handlers(self, topic: str) -> Dict[str, Callable[[Message], None]]:
        return self.callback_handlers.get(topic, {})

    def get_subscribers(self, topic: str) -> Set[str]:
        return self.subscribers.get(topic, set())

    def get_all_subscribers(self) -> Dict[str, Set[str]]:
        return self.subscribers

    def get_all_topics(self) -> Dict[str, List[Message]]:
        return self.topics

    def subscribe(self, topic: str, subscriber: str, handler: Callable[[Message], None]) -> None:
        if topic not in self.subscribers:
            self.subscribers[topic] = set()
        self.subscribers[topic].add(subscriber)

        if topic not in self.callback_handlers:
            self.callback_handlers[topic] = {}
        self.callback_handlers[topic][subscriber] = handler

    def unsubscribe(self, topic: str, subscriber: str) -> None:
        if topic in self.subscribers:
            self.subscribers[topic].discard(subscriber)
        if topic in self.callback_handlers:
            self.callback_handlers[topic].pop(subscriber, None)

    def cleanup(self) -> None:
        self.topics = {}

    @classmethod
    def get_instance(cls) -> "MemoryStore":
        if cls._instance is None:
            cls._instance = MemoryStore()
        cls._instance_count += 1  # Helpful in debugging
        return cls._instance


class InMemoryMessagingBackend(MessagingBackend):
    """
    InMemoryStorage provides an in-memory backend mechanism for the message bus.

    NOTE: DO NOT USE IN PRODUCTION. This is a simple implementation for development/testing purposes only.

    Attributes:
        - topics (Dict[str, List[Message]]): A dictionary mapping topics to their sorted list of messages.
        - subscribers (Dict[str, Set[str]]): A dictionary mapping topics to sets of subscribed client IDs.
    """

    def __init__(self) -> None:
        """
        Initializes the in-memory backend with empty dictionaries for topics and subscribers.
        """
        self.subscriber_id = shortuuid.uuid()
        self.subscribers: Dict[str, Set[str]] = {}
        self.callback_handlers: Dict[str, Dict[str, Callable[[Message], None]]] = {}
        self._message_store = MemoryStore.get_instance()

    def store_message(self, topic: str, message: Message) -> None:
        """
        Add a message to a topic. Messages are stored in a sorted manner based on timestamp.

        Args:
            topic (str): The topic to which the message belongs.
            message (Message): The message to be added.
        """

        self._message_store.store_message(topic, message)

        # We want to send the notification to all global subscribers that may have connected through all instances of the backend.
        if self._message_store.get_subscribers(topic):
            for handler in self._message_store.get_callback_handlers(topic).values():
                handler(message.model_copy(deep=True))

    def get_messages_for_topic(self, topic: str) -> List[Message]:
        """
        Retrieve all messages for a given topic.

        Args:
            topic (str): The topic to retrieve messages for.

        Returns:
            List[Message]: A list of messages for the given topic.
        """
        return self._message_store.get_messages_for_topic(topic)

    def get_messages_for_topic_since(self, topic: str, msg_id_since: int) -> List[Message]:
        """
        Retrieve all messages for a given topic since a given message ID.

        Args:
            topic (str): The topic to retrieve messages for.
            msg_id_since (int): The ID of the message since which to retrieve messages.

        Returns:
            List[Message]: A list of messages for the given topic since the given message ID.
        """
        timestamp_since = self._get_timestamp_for_id(msg_id_since)
        return self._message_store.get_messages_for_topic_since(topic, timestamp_since)

    def get_next_message_for_topic_since(self, topic: str, last_message_id: int) -> Optional[Message]:
        """
        Retrieve the next message for a given topic since a given message ID.

        Args:
            topic (str): The topic to retrieve messages for.
            last_message_id (int): The ID of the last message received.

        Returns:
            Message: The next message for the given topic since the given message ID.
        """
        timestamp_since = self._get_timestamp_for_id(last_message_id)
        return self._message_store.get_next_message_for_topic_since(topic, timestamp_since)

    def load_subscribers(self, namespace: str) -> Dict[str, Set[str]]:
        """
        Load all subscribers from the in-memory backend.

        Returns:
            Dict[str, Set[str]]: A dictionary mapping topics to sets of client IDs.
        """
        # Only return the subscribers that are relevant to the current instance of the backend.
        return self.subscribers

    def subscribe(self, topic: str, handler: Callable[[Message], None]) -> None:
        if topic not in self.subscribers:
            self.subscribers[topic] = set()
        self.subscribers[topic].add(self.subscriber_id)

        if topic not in self.callback_handlers:
            self.callback_handlers[topic] = {}
        self.callback_handlers[topic][self.subscriber_id] = handler

        self._message_store.subscribe(topic, self.subscriber_id, handler)

    def unsubscribe(self, topic: str) -> None:
        if topic in self.subscribers:
            self.subscribers[topic].discard(self.subscriber_id)
        if topic in self.callback_handlers:
            self.callback_handlers[topic].pop(self.subscriber_id, None)

        self._message_store.unsubscribe(topic, self.subscriber_id)

    def cleanup(self) -> None:
        """
        Cleanup the in-memory backend by removing all messages and subscribers.
        """
        self._message_store.cleanup()

    def supports_subscription(self) -> bool:
        return True
