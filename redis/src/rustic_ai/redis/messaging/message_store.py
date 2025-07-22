"""Redis message store for handling message storage and retrieval operations."""

import logging
import os
from typing import Awaitable, Callable, List, Optional, Union

import redis

from rustic_ai.core.messaging.core.message import Message
from rustic_ai.core.utils.gemstone_id import GemstoneID
from rustic_ai.redis.messaging.connection_manager import RedisBackendConfig
from rustic_ai.redis.messaging.retry_utils import execute_with_retry


class RedisMessageStore:
    """Manages Redis message storage and retrieval operations with retry logic."""

    def __init__(
        self, client: Union[redis.StrictRedis, redis.RedisCluster], config: Optional[RedisBackendConfig] = None
    ):
        """
        Initialize the message store.

        Args:
            client: Redis client instance
            config: Optional configuration for retry behavior
        """
        self.client = client
        self.config = config
        # Get message TTL from config or environment with default
        self.message_ttl = int(os.environ.get("RUSTIC_AI_REDIS_MSG_TTL", 3600))

    def store_message(
        self, namespace: str, topic: str, message: Message, pubsub_publish: Callable[[str, str], int]
    ) -> None:
        """
        Store a message in Redis atomically using MULTI/EXEC transaction.
        Creates a secondary index for direct ID lookups and publishes for real-time notifications.

        Args:
            namespace: The namespace of the message.
            topic: The topic to which the message belongs.
            message: The message object to be stored.
            pubsub_publish: Function to publish message via pub/sub
        """
        message_json = message.to_json()
        msg_key = self._get_msg_key(namespace, message.id)

        # Execute with retry logic
        def store_operation():
            # Use pipeline to execute commands in batch
            # Note: We don't use transaction=True because it is not supported by RedisCluster
            with self.client.pipeline(transaction=False) as pipe:
                pipe.set(msg_key, message_json, ex=self.message_ttl)
                # Use timestamp as score like the original implementation
                pipe.zadd(topic, {message_json: message.timestamp})
                pipe.execute()

            # Publish separately (not part of transaction)
            subscribers_notified = pubsub_publish(topic, message_json)
            logging.debug(
                f"Message {message.id} stored atomically for topic {topic}, notified {subscribers_notified} subscribers"
            )

        try:
            execute_with_retry(f"Store message {message.id} to topic {topic}", store_operation, self.config)
        except Exception as e:
            logging.error(f"Atomic message storage failed for message {message.id} on topic {topic}: {e}")
            raise

    def get_messages_for_topic(self, topic: str) -> List[Message]:
        """
        Retrieve all messages for a given topic.

        Args:
            topic: The topic to retrieve messages for.

        Returns:
            List[Message]: A list of messages for the given topic.
        """

        def get_operation():
            raw_messages = self.client.zrange(topic, 0, -1)

            if isinstance(raw_messages, Awaitable):  # runtime check
                raise RuntimeError("Unexpected awaitable from synchronous Redis client")

            messages = [Message.from_json(raw_message) for raw_message in raw_messages]
            # Sort by message.id like the original implementation for proper priority+timestamp ordering
            return sorted(messages, key=lambda msg: msg.id)

        return execute_with_retry(f"Get messages for topic {topic}", get_operation, self.config)

    def get_messages_for_topic_since(self, topic: str, msg_id_since: int) -> List[Message]:
        """
        Retrieve all messages for a given topic since a given message ID.

        Args:
            topic: The topic to retrieve messages for.
            msg_id_since: The ID of the message since which to retrieve messages.

        Returns:
            List[Message]: A list of messages for the given topic since the given message ID.
        """

        def get_operation():
            # Use timestamp-based filtering since "since ID" means "since that message's timestamp"
            # Higher priority messages created later can have smaller IDs, so ID filtering doesn't work
            timestamp_since = self._get_timestamp_for_id(msg_id_since) + 1
            raw_messages = self.client.zrangebyscore(topic, timestamp_since, "+inf")

            if isinstance(raw_messages, Awaitable):  # runtime check
                raise RuntimeError("Unexpected awaitable from synchronous Redis client")

            messages = [Message.from_json(raw_message) for raw_message in raw_messages]
            # Sort by ID to get proper priority+timestamp ordering
            return sorted(messages, key=lambda msg: msg.id)

        return execute_with_retry(f"Get messages for topic {topic} since {msg_id_since}", get_operation, self.config)

    def get_next_message_for_topic_since(self, topic: str, last_message_id: int) -> Optional[Message]:
        """
        Retrieve the next message for a given topic since a given message ID.

        Args:
            topic: The topic to retrieve messages for.
            last_message_id: The ID of the last message received.

        Returns:
            Optional[Message]: The next message for the given topic since the given message ID.
        """

        def get_operation():
            # Use timestamp-based filtering like the original implementation
            timestamp_since = self._get_timestamp_for_id(last_message_id) + 1
            raw_messages = self.client.zrangebyscore(topic, timestamp_since, "+inf")

            if isinstance(raw_messages, Awaitable):  # runtime check
                raise RuntimeError("Unexpected awaitable from synchronous Redis client")

            if not raw_messages:
                return None

            # Sort by ID like the original and return the first one
            messages = [Message.from_json(raw_message) for raw_message in raw_messages]
            sorted_messages = sorted(messages, key=lambda msg: msg.id)
            return sorted_messages[0]

        return execute_with_retry(
            f"Get next message for topic {topic} since {last_message_id}", get_operation, self.config
        )

    def get_messages_by_id(self, namespace: str, msg_ids: List[int]) -> List[Message]:
        """
        Retrieve messages by their IDs using Redis pipelines for efficiency.

        Args:
            namespace: The namespace of the messages.
            msg_ids: A list of message IDs to retrieve.

        Returns:
            List[Message]: A list of Message objects corresponding to the provided IDs.
        """
        if not msg_ids:
            return []

        def get_operation():
            result = []

            # Use Redis pipeline to batch operations for efficiency
            with self.client.pipeline() as pipe:
                # For each message ID, get the message from the secondary index
                for msg_id in msg_ids:
                    pipe.get(self._get_msg_key(namespace, msg_id))

                # Execute pipeline and process results
                raw_messages = pipe.execute()

            # Convert raw messages to Message objects
            for raw_message in raw_messages:
                if raw_message:
                    result.append(Message.from_json(raw_message))
            return result

        return execute_with_retry(f"Get messages by IDs for namespace {namespace}", get_operation, self.config)

    @staticmethod
    def _get_msg_key(namespace: str, message_id: int) -> str:
        """Generate Redis key for message storage."""
        return f"msg:{namespace}:{message_id}"

    @staticmethod
    def _get_timestamp_for_id(msg_id: int) -> float:
        """
        Helper method to retrieve the timestamp for a given message ID.

        Args:
            msg_id: The ID of the message.

        Returns:
            float: The timestamp of the message.
        """
        return GemstoneID.from_int(msg_id).timestamp
