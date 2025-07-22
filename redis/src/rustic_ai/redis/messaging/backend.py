from typing import Callable, Dict, List, Optional, Set, Union

import redis

from rustic_ai.core.messaging.core.message import Message
from rustic_ai.core.messaging.core.messaging_backend import MessagingBackend
from rustic_ai.core.utils import GemstoneID
from rustic_ai.redis.messaging.connection_manager import (
    RedisBackendConfig,
    RedisConnectionManager,
)
from rustic_ai.redis.messaging.message_store import RedisMessageStore
from rustic_ai.redis.messaging.pubsub_manager import RedisPubSubManager


class RedisMessagingBackend(MessagingBackend):
    """Redis implementation of the MessagingBackend interface."""

    def __init__(self, redis_client: Union[redis.StrictRedis, RedisBackendConfig, dict]) -> None:
        """
        Initialize with a Redis client.

        Args:
            redis_client: A Redis client instance, configuration dict, or RedisBackendConfig.
        """
        # Initialize connection manager
        self._connection_manager = RedisConnectionManager(redis_client)

        # Get client and config from connection manager
        self.r = self._connection_manager.get_client()
        config = self._connection_manager.get_config()

        # Initialize message store
        self._message_store = RedisMessageStore(self.r, config)

        # Initialize pub/sub manager
        self._pubsub_manager = RedisPubSubManager(self.r, config)

        # Setup pub/sub connection
        self._pubsub_manager.setup()

    def store_message(self, namespace: str, topic: str, message: Message) -> None:
        """
        Store a message in Redis atomically.

        Args:
            namespace: The namespace of the message.
            topic: The topic to which the message belongs.
            message: The message object to be stored.
        """
        # Use message store with pub/sub publish callback
        self._message_store.store_message(namespace, topic, message, self._pubsub_manager.publish)

    def get_messages_for_topic(self, topic: str) -> List[Message]:
        """
        Retrieve all messages for a given topic.

        Args:
            topic: The topic to retrieve messages for.

        Returns:
            List[Message]: A list of messages for the given topic.
        """
        return self._message_store.get_messages_for_topic(topic)

    def get_messages_for_topic_since(self, topic: str, msg_id_since: int) -> List[Message]:
        """
        Retrieve all messages for a given topic since a given message ID.

        Args:
            topic: The topic to retrieve messages for.
            msg_id_since: The ID of the message since which to retrieve messages.

        Returns:
            List[Message]: A list of messages for the given topic since the given message ID.
        """
        return self._message_store.get_messages_for_topic_since(topic, msg_id_since)

    def get_next_message_for_topic_since(self, topic: str, last_message_id: int) -> Optional[Message]:
        """
        Retrieve the next message for a given topic since a given message ID.

        Args:
            topic: The topic to retrieve messages for.
            last_message_id: The ID of the last message received.

        Returns:
            Optional[Message]: The next message for the given topic since the given message ID.
        """
        return self._message_store.get_next_message_for_topic_since(topic, last_message_id)

    def load_subscribers(self, namespace: str) -> Dict[str, Set[str]]:
        """
        Load all subscribers from Redis.

        Returns:
            Dict[str, Set[str]]: A dictionary mapping topics to sets of client IDs.
        """
        # TBD: Implement the logic to load subscribers.
        return {}

    def subscribe(self, topic: str, handler: Callable[[Message], None]) -> None:
        """
        Subscribe to a topic and handle incoming messages.

        Args:
            topic: The topic to subscribe to.
            handler: The handler function to handle incoming messages.
        """
        self._pubsub_manager.subscribe(topic, handler)

    def unsubscribe(self, topic: str) -> None:
        """
        Unsubscribe from a topic.

        Args:
            topic: The topic to unsubscribe from.
        """
        self._pubsub_manager.unsubscribe(topic)

    def cleanup(self) -> None:
        """
        Clean up the Redis storage.
        """
        # Clean up pub/sub manager
        self._pubsub_manager.cleanup()

        # Close Redis connection
        self._connection_manager.close()

    def supports_subscription(self) -> bool:
        """Check if this backend supports pub/sub subscriptions."""
        return True

    def get_messages_by_id(self, namespace: str, msg_ids: List[int]) -> List[Message]:
        """
        Retrieve messages by their IDs.

        Args:
            namespace: The namespace of the messages.
            msg_ids: A list of message IDs to retrieve.

        Returns:
            List[Message]: A list of Message objects corresponding to the provided IDs.
        """
        return self._message_store.get_messages_by_id(namespace, msg_ids)

    def set_failure_callback(self, callback: Optional[Callable[[Exception], None]]) -> None:
        """Set a custom failure callback for testing purposes."""
        self._pubsub_manager.set_failure_callback(callback)

    def _get_timestamp_for_id(self, msg_id: int) -> float:
        """
        Helper method to retrieve the timestamp for a given message ID.

        Args:
            msg_id: The ID of the message.

        Returns:
            float: The timestamp of the message.
        """
        return GemstoneID.from_int(msg_id).timestamp

    @property
    def _config(self) -> Optional[RedisBackendConfig]:
        """Get the Redis configuration (for testing purposes)."""
        return self._connection_manager.get_config()
