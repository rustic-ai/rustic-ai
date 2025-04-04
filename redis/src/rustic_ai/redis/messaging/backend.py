import logging
from typing import Callable, Dict, List, Optional, Set, Union

from pydantic import BaseModel, Field

import redis
from rustic_ai.core.messaging.core.message import Message
from rustic_ai.core.messaging.core.messaging_backend import MessagingBackend
from rustic_ai.core.utils import GemstoneID


class RedisBackendConfig(BaseModel):
    host: str
    port: int
    username: Optional[str] = Field(default=None)
    password: Optional[str] = Field(default=None)
    ssl: bool = Field(default=False)
    ssl_certfile: Optional[str] = Field(default=None)
    ssl_keyfile: Optional[str] = Field(default=None)
    ssl_ca_certs: Optional[str] = Field(default=None)
    is_cluster: bool = Field(default=False)


class RedisMessagingBackend(MessagingBackend):
    def __init__(self, redis_client: Union[redis.StrictRedis, RedisBackendConfig, dict]) -> None:
        """
        Initialize with a Redis client.

        Args:
            redis_client: A Redis client instance.
        """
        self.r: redis.StrictRedis | redis.RedisCluster
        if isinstance(redis_client, dict):
            redis_client = RedisBackendConfig(**redis_client)

        if isinstance(redis_client, RedisBackendConfig):
            if redis_client.is_cluster:
                self.r = redis.RedisCluster(
                    host=redis_client.host,
                    port=redis_client.port,
                    username=redis_client.username,
                    password=redis_client.password,
                    ssl=redis_client.ssl,
                    ssl_certfile=redis_client.ssl_certfile,
                    ssl_keyfile=redis_client.ssl_keyfile,
                    ssl_ca_certs=redis_client.ssl_ca_certs,
                )
            else:
                self.r = redis.StrictRedis(
                    host=redis_client.host,
                    port=redis_client.port,
                    username=redis_client.username,
                    password=redis_client.password,
                    ssl=redis_client.ssl,
                    ssl_certfile=redis_client.ssl_certfile,
                    ssl_keyfile=redis_client.ssl_keyfile,
                    ssl_ca_certs=redis_client.ssl_ca_certs,
                )
        elif isinstance(redis_client, redis.StrictRedis):
            self.r = redis_client
        else:
            raise ValueError("Invalid Redis client")  # pragma: no cover

        self.p = self.r.pubsub(ignore_subscribe_messages=True)
        self.redis_thread = self.p.run_in_thread(sleep_time=0.001, daemon=True)

    def store_message(self, topic: str, message: Message) -> None:
        """
        Store a message in Redis, sorted by timestamp.

        Args:
            message (Message): The message object to be stored.
        """
        # Using the timestamp as the score for sorting in Redis sorted set.
        self.r.zadd(topic, {message.to_json(): message.timestamp})
        self.r.publish(topic, message.to_json())

    def get_messages_for_topic(self, topic: str) -> List[Message]:
        """
        Retrieve all messages for a given topic.

        Args:
            topic (str): The topic to retrieve messages for.

        Returns:
            List[Message]: A list of messages for the given topic.
        """
        raw_messages = self.r.zrange(topic, 0, -1)
        messages = [Message.from_json(raw_message) for raw_message in raw_messages]
        return sorted(messages, key=lambda msg: msg.id)

    def get_messages_for_topic_since(self, topic: str, msg_id_since: int) -> List[Message]:
        """
        Retrieve all messages for a given topic since a given message ID.

        Args:
            topic (str): The topic to retrieve messages for.
            msg_id_since (int): The ID of the message since which to retrieve messages.

        Returns:
            List[Message]: A list of messages for the given topic since the given message ID.
        """
        # Retrieve the timestamp corresponding to the given message ID.
        timestamp_since = self._get_timestamp_for_id(msg_id_since) + 1
        raw_messages = self.r.zrangebyscore(topic, timestamp_since, "+inf")
        messages = [Message.from_json(raw_message) for raw_message in raw_messages]
        return sorted(messages, key=lambda msg: msg.id)

    def get_next_message_for_topic_since(self, topic: str, last_message_id: int) -> Optional[Message]:
        """
        Retrieve the next message for a given topic since a given message ID.

        Args:
            topic (str): The topic to retrieve messages for.
            last_message_id (int): The ID of the last message received.

        Returns:
            Optional[Message]: The next message for the given topic since the given message ID.
        """
        timestamp_since = self._get_timestamp_for_id(last_message_id) + 1
        raw_messages = self.r.zrangebyscore(topic, timestamp_since, "+inf", start=0, num=1)
        return Message.from_json(raw_messages[0]) if raw_messages else None

    def load_subscribers(self, namespace: str) -> Dict[str, Set[str]]:
        """
        Load all subscribers from Redis.

        Returns:
            Dict[str, Set[str]]: A dictionary mapping topics to sets of client IDs.
        """
        # TBD: Implement the logic to load subscribers.
        return {}

    def _get_timestamp_for_id(self, msg_id: int) -> float:
        """
        Helper method to retrieve the timestamp for a given message ID.

        Args:
            msg_id (int): The ID of the message.

        Returns:
            float: The timestamp of the message.
        """
        # Implement logic to retrieve the timestamp from a message ID.
        # This method needs to be adjusted based on how the timestamp is stored or derived from the message ID.
        return GemstoneID.from_int(msg_id).timestamp

    def subscribe(self, topic: str, handler: Callable[[Message], None]) -> None:
        """
        Subscribe to a topic and handle incoming messages.

        Args:
            topic (str): The topic to subscribe to.
            handler (Callable[[Message], None]): The handler function to handle incoming messages.
        """

        def _handler(redis_message: Dict) -> None:
            logging.debug(f"[RedisStorage] Received message: {redis_message}")
            handler(Message.from_json(redis_message["data"]))

        logging.debug(f"Subscribing to topic: {topic}")

        self.p.subscribe(**{topic: _handler})

    def unsubscribe(self, topic: str) -> None:
        """
        Unsubscribe from a topic.

        Args:
            topic (str): The topic to unsubscribe from.
        """
        logging.debug(f"Unsubscribing from topic: {topic}")
        self.p.unsubscribe(topic)
        logging.debug(f"Unsubscribed from topic: {topic}")

    def cleanup(self) -> None:
        """
        Clean up the Redis storage.
        """
        self.redis_thread.stop()
        self.redis_thread.join(timeout=1)
        self.p.close()
        self.r.close()

    def supports_subscription(self) -> bool:
        return True
