"""NATS messaging backend facade."""

from typing import Callable, Dict, List, Optional, Set, Union

from rustic_ai.core.messaging.core.message import Message
from rustic_ai.core.messaging.core.messaging_backend import MessagingBackend
from rustic_ai.core.utils import GemstoneID
from rustic_ai.nats.messaging.connection_manager import (
    NATSBackendConfig,
    NATSConnectionManager,
)
from rustic_ai.nats.messaging.message_store import NATSMessageStore
from rustic_ai.nats.messaging.pubsub_manager import NATSPubSubManager


class NATSMessagingBackend(MessagingBackend):
    """NATS implementation of the MessagingBackend interface."""

    def __init__(self, nats_client: Union[object, NATSBackendConfig, dict]) -> None:
        """
        Initialize with a NATS client, config, or dict.

        Args:
            nats_client: A NATS client instance, NATSBackendConfig, or configuration dict.
        """
        # Initialize connection manager (creates async event loop bridge)
        self._connection_manager = NATSConnectionManager(nats_client)

        config = self._connection_manager.get_config()

        # Initialize message store
        self._message_store = NATSMessageStore(
            self._connection_manager.get_js(),
            self._connection_manager.run_async,
            config,
        )

        # Initialize pub/sub manager (pass js + ensure_stream for per-client push consumers)
        self._pubsub_manager = NATSPubSubManager(
            self._connection_manager.get_client(),
            self._connection_manager.get_js(),
            self._connection_manager.run_async,
            config,
            ensure_stream=self._message_store._ensure_stream,
        )

        self._pubsub_manager.setup()

    def store_message(self, namespace: str, topic: str, message: Message) -> None:
        """Store a message durably and publish for real-time notification."""
        self._message_store.store_message(namespace, topic, message, self._pubsub_manager.publish)

    def get_messages_for_topic(self, topic: str) -> List[Message]:
        """Retrieve all messages for a given topic."""
        return self._message_store.get_messages_for_topic(topic)

    def get_messages_for_topic_since(self, topic: str, msg_id_since: int) -> List[Message]:
        """Retrieve all messages for a given topic since a given message ID."""
        return self._message_store.get_messages_for_topic_since(topic, msg_id_since)

    def get_next_message_for_topic_since(self, topic: str, last_message_id: int) -> Optional[Message]:
        """Retrieve the next message for a given topic since a given message ID."""
        return self._message_store.get_next_message_for_topic_since(topic, last_message_id)

    def load_subscribers(self, namespace: str) -> Dict[str, Set[str]]:
        """Load subscribers for a namespace (TBD implementation)."""
        return {}

    def subscribe(self, topic: str, handler: Callable[[Message], None], client_id: Optional[str] = None) -> None:
        """Subscribe to a topic.

        When client_id is provided, uses per-client durable push consumer with delivery guarantees.
        """
        self._pubsub_manager.subscribe(topic, handler, client_id=client_id)

    def unsubscribe(self, topic: str, client_id: Optional[str] = None) -> None:
        """Unsubscribe from a topic."""
        self._pubsub_manager.unsubscribe(topic, client_id=client_id)

    def cleanup(self) -> None:
        """Clean up all resources."""
        self._pubsub_manager.cleanup()
        self._connection_manager.close()

    def supports_subscription(self) -> bool:
        """NATS supports pub/sub subscriptions."""
        return True

    def get_messages_by_id(self, namespace: str, msg_ids: List[int]) -> List[Message]:
        """Retrieve messages by their IDs."""
        return self._message_store.get_messages_by_id(namespace, msg_ids)

    def set_failure_callback(self, callback: Optional[Callable[[Exception], None]]) -> None:
        """Set a custom failure callback for testing purposes."""
        self._pubsub_manager.set_failure_callback(callback)

    def _get_timestamp_for_id(self, msg_id: int) -> float:
        """Helper to retrieve the timestamp for a given message ID."""
        return GemstoneID.from_int(msg_id).timestamp

    @property
    def _config(self) -> Optional[NATSBackendConfig]:
        """Get the NATS configuration (for testing purposes)."""
        return self._connection_manager.get_config()
