import logging
from typing import Callable, Dict, List, Optional, Set

from rustic_ai.core.guild.dsl import GuildTopics
from rustic_ai.core.messaging.core.client import Client
from rustic_ai.core.messaging.core.message import Message
from rustic_ai.core.messaging.core.messaging_config import MessagingConfig


class MessagingInterface:
    """
    A message bus that handles the publishing and subscribing of messages.

    The Messaging Interface is responsible for:
    - Registering and unregistering clients.
    - Publishing messages to topics.
    - Subscribing clients to specific topics.
    - Retrieving messages for a given topic.
    - Notifying clients of new messages.

    Attributes:
        backend (MessagingBackend): The storage backend used to persist messages and client information.
        clients (Dict[str, Client]): A dictionary mapping client IDs to Client instances.
        subscribers (Dict[str, Set[str]]): A dictionary mapping topics to sets of client IDs.
        shared_namespace (Optional[str]): The shared namespace for cross-guild communication (organization ID).
        shared_subscribers (Dict[str, Set[str]]): Subscribers for shared namespace topics.
    """

    def __init__(self, namespace: str, messaging_config: MessagingConfig):
        """
        Initializes the Messaging Interface with a given storage backend.

        Args:
            backend (MessagingConfig): The configuration for the backend to use.
        """
        logging.info(f"Initializing backend from config: {messaging_config}")
        try:
            self.backend = messaging_config.get_storage()
        except Exception as e:  # pragma: no cover
            logging.exception(f"Error initializing storage backend: {e}")
            raise ValueError(f"Error initializing storage backend: {e}")
        logging.info(f"Using Backend: {messaging_config}")

        self.clients: Dict[str, Client] = {}
        self.subscribers: Dict[str, Set[str]] = self.backend.load_subscribers(namespace)
        self.namespace = namespace

        # Shared namespace for cross-guild communication (lazy initialized)
        self.shared_namespace: Optional[str] = None
        self.shared_subscribers: Dict[str, Set[str]] = {}

    def _get_namespaced_topics(self, topics: List[str]) -> Dict[str, str]:
        """
        Get the fully qualified topic name.

        Args:
            topics (str): The topic to use.

        Returns:
            List[str]: The fully qualified topic names.
        """
        return {topic: self._get_namespaced_topic(topic) for topic in topics}

    def _get_namespaced_topic(self, topic: str) -> str:
        if topic.startswith(f"{self.namespace}:"):
            return topic
        else:
            return f"{self.namespace}:{topic}"

    def _get_namespaced_topics_for_message(self, message: Message) -> Dict[str, str]:
        """
        Get the fully qualified topic name for a message.

        Args:
            message (Message): The message to use.

        Returns:
            str: The fully qualified topic name for the message.
        """
        topics = message.topics if isinstance(message.topics, list) else [message.topics]
        return self._get_namespaced_topics(topics)

    def register_client(self, client: Client) -> None:
        """
        Register a new client with the Messaging Interface.

        Args:
            client (Client): The client instance to register.
        """
        self.clients[client.id] = client
        client.connect(self)

    def unregister_client(self, client: Client) -> None:
        """
        Unregister a client from the Messaging Interface.

        Args:
            client (Client): The client instance to unregister.
        """
        if client.id in self.clients:
            self.clients.pop(client.id, None)
            client.disconnect()

    def publish(self, sender: Client, message: Message) -> None:
        """
        Publish a message to a specific topic.

        Args:
            sender (Client): The client that published the message.
            message (Message): The message instance to publish.
        """
        topics = self._get_namespaced_topics_for_message(message)
        for otopic, ntopic in topics.items():
            logging.debug(f"[Messaging] Publishing message to topic {ntopic}")
            message_copy = message.model_copy(deep=True)
            message_copy.topic_published_to = otopic
            self.backend.store_message(self.namespace, ntopic, message_copy)

    def _enrich_message(self, message: Message) -> None:
        """
        Enrich a message with its history if requested.

        Args:
            message (Message): The message to enrich in place.
        """
        if message.enrich_with_history:
            fetch_length = (
                message.enrich_with_history
                if message.enrich_with_history < len(message.message_history)
                else len(message.message_history)
            )
            previous_msg_ids = [entry.origin for entry in message.message_history[-fetch_length:]]
            previous_messages = self.backend.get_messages_by_id(self.namespace, previous_msg_ids)
            # excluding session_state of previous messages from enriched_history to avoid serialization issues
            prev_messages_json = [
                msg.model_dump_json(exclude={"current_thread_id", "root_thread_id", "session_state"})
                for msg in previous_messages
            ]
            if message.session_state is None:
                message.session_state = {}
            message.session_state["enriched_history"] = prev_messages_json

    def _should_deliver_to(self, message: Message, client: Client) -> bool:
        """
        Determine whether a message should be delivered to a given client.

        Applies self-send filtering: sender does not receive its own messages on normal topics,
        but does receive on self-inbox topics.

        Args:
            message (Message): The message to evaluate.
            client (Client): The client to evaluate delivery for.

        Returns:
            bool: True if the message should be delivered.
        """
        assert message.topic_published_to is not None
        recipient_id = client.id.split("$")[-1]
        if (
            recipient_id != message.sender.id
            and not message.topic_published_to.startswith(f"{GuildTopics.AGENT_SELF_INBOX_PREFIX}")
        ):
            return True
        elif (
            recipient_id == message.sender.id
            and message.topic_published_to.startswith(f"{GuildTopics.AGENT_SELF_INBOX_PREFIX}")
        ):
            return True
        return False

    def _make_client_handler(self, client: Client) -> Callable[[Message], None]:
        """
        Create a per-client message handler closure with enrichment and self-send filtering.

        Args:
            client (Client): The client to create a handler for.

        Returns:
            Callable[[Message], None]: A handler that enriches and filters messages before delivering.
        """

        def handler(message: Message) -> None:
            self._enrich_message(message)
            if self._should_deliver_to(message, client):
                client.notify_new_message(message)

        return handler

    def subscribe(self, topic: str, client: Client) -> None:
        """
        Subscribe a client to a specific topic.

        Args:
            topic (str): The topic to subscribe to.
            client (Client): The client instance to subscribe.
        """
        namespaced_topic = self._get_namespaced_topic(topic)

        logging.debug(f"[Messaging] Subscribing client {client.id} to topic {namespaced_topic}")

        if namespaced_topic not in self.subscribers:
            self.subscribers[namespaced_topic] = set()
        self.subscribers[namespaced_topic].add(client.id)

        handler = self._make_client_handler(client)
        self.backend.subscribe(namespaced_topic, handler, client_id=client.id, namespace=self.namespace)

    def unsubscribe(self, topic: str, client: Client) -> None:
        """
        Unsubscribe a client from a specific topic.

        Args:
            topic (str): The topic to unsubscribe from.
            client (Client): The client instance to unsubscribe.
        """
        namespaced_topic = self._get_namespaced_topic(topic)
        if namespaced_topic in self.subscribers:
            self.subscribers[namespaced_topic].discard(client.id)
            if not self.subscribers[namespaced_topic]:
                self.subscribers.pop(namespaced_topic, None)
        self.backend.unsubscribe(namespaced_topic, client_id=client.id)

    def get_messages(self, topic: str) -> List[Message]:
        """
        Retrieve all messages for a given topic.

        Args:
            topic (str): The topic to retrieve messages for.

        Returns:
            List[Message]: A list of messages for the given topic.
        """

        return self.backend.get_messages_for_topic(self._get_namespaced_topic(topic))

    def get_messages_for_topic_since(self, topic: str, msg_id_since: int) -> List[Message]:
        """
        Retrieve all messages for a given topic since a specific message ID.

        Args:
            topic (str): The topic to retrieve messages for.
            msg_id_since (int): The message ID to start retrieving from. If 0, retrieves from the beginning.

        Returns:
            List[Message]: A list of messages for the given topic since the specified message ID.
        """
        return self.backend.get_messages_for_topic_since(self._get_namespaced_topic(topic), msg_id_since)

    def get_next_message_for_topic(self, topic: str, last_message_id: int) -> Optional[Message]:
        """
        Retrieve the next message for a given topic since a specific message ID.

        Args:
            topic (str): The topic to retrieve messages for.
            last_message_id (int): The message ID to start retrieving from. If 0, retrieves from the beginning.

        Returns:
            Message: A message for the given topic since the specified message ID.
        """
        return self.backend.get_next_message_for_topic_since(self._get_namespaced_topic(topic), last_message_id)

    def get_messages_for_client_since(self, client_id: str, msg_id_since: int) -> List[Message]:
        """
        Retrieve all messages for a given client since a specific message ID.

        Args:
            client_id (str): The ID of the client to retrieve messages for.
            msg_id_since (int): The message ID to start retrieving from.

        Returns:
            List[Message]: A list of messages for the given client since the specified message ID.
        """
        # Get all topics subscribed to by the client
        subscribed_topics = [topic for topic, clients in self.subscribers.items() if client_id in clients]

        # Get all the messages for those topics since the message ID
        all_messages = []
        for topic in subscribed_topics:
            all_messages.extend(self.backend.get_messages_for_topic_since(topic, msg_id_since))

        # Sort the messages by ID
        sorted_messages = sorted(all_messages, key=lambda msg: msg.id)

        return sorted_messages

    def get_next_message_for_client(self, client_id: str, last_message_id: int) -> Optional[Message]:
        """
        Retrieve the next message for a given client since a specific message ID.

        Args:
            client_id (str): The ID of the client to retrieve messages for.
            last_message_id (int): The message ID to start retrieving from.

        Returns:
            Message: The next message for the given client since the specified message ID.
        """
        messages = self.get_messages_for_client_since(client_id, last_message_id)
        return messages[0] if messages else None

    def shutdown(self) -> None:
        """
        Shutdown the message bus and clean up resources.
        """
        for client in self.clients.values():
            try:
                client.disconnect()
            except Exception:
                logging.exception("Error disconnecting client %s", client.id)
        self.backend.cleanup()
        self.clients = {}
        self.subscribers = {}
        self.shared_subscribers = {}

    # =========================================================================
    # Shared Namespace Methods (for cross-guild communication)
    # =========================================================================

    def activate_shared_namespace(self, shared_namespace: str) -> None:
        """
        Activate shared namespace for cross-guild communication.
        Called by BoundaryClient when needed.

        Args:
            shared_namespace: The organization ID to use as shared namespace.

        Raises:
            RuntimeError: If shared namespace is already activated with a different value.
        """
        if self.shared_namespace is not None:
            if self.shared_namespace != shared_namespace:
                raise RuntimeError(
                    f"Shared namespace already activated as '{self.shared_namespace}', "
                    f"cannot change to '{shared_namespace}'"
                )
            return  # Already activated with same namespace

        logging.info(f"Activating shared namespace: {shared_namespace}")
        self.shared_namespace = shared_namespace
        self.shared_subscribers = self.backend.load_subscribers(shared_namespace)

    def _get_shared_namespaced_topic(self, topic: str) -> str:
        """
        Get the fully qualified topic name in the shared namespace.

        Args:
            topic: The topic to namespace.

        Returns:
            The namespaced topic string.

        Raises:
            RuntimeError: If shared namespace is not activated.
        """
        if self.shared_namespace is None:
            raise RuntimeError("Shared namespace not activated")
        if topic.startswith(f"{self.shared_namespace}:"):
            return topic
        return f"{self.shared_namespace}:{topic}"

    def publish_to_shared(self, sender: Client, message: Message) -> None:
        """
        Publish a message to the shared namespace.

        Args:
            sender: The client that published the message.
            message: The message instance to publish.

        Raises:
            RuntimeError: If shared namespace is not activated.
        """
        if self.shared_namespace is None:
            raise RuntimeError("Shared namespace not activated")

        topics = message.topics if isinstance(message.topics, list) else [message.topics]
        for topic in topics:
            ntopic = self._get_shared_namespaced_topic(topic)
            logging.debug(f"[Messaging] Publishing message to shared namespace topic {ntopic}")
            message_copy = message.model_copy(deep=True)
            message_copy.topic_published_to = topic
            self.backend.store_message(self.shared_namespace, ntopic, message_copy)

    def _make_shared_client_handler(self, client: Client) -> Callable[[Message], None]:
        """
        Create a per-client handler for shared namespace topics.

        Shared topics don't have self-inbox semantics — sender simply never receives its own messages.

        Args:
            client (Client): The client to create a handler for.

        Returns:
            Callable[[Message], None]: A handler that filters self-sends before delivering.
        """

        def handler(message: Message) -> None:
            recipient_id = client.id.split("$")[-1]
            if recipient_id != message.sender.id:
                client.notify_new_message(message)

        return handler

    def subscribe_shared(self, topic: str, client: Client) -> None:
        """
        Subscribe a client to a topic in the shared namespace.

        Args:
            topic: The topic to subscribe to.
            client: The client instance to subscribe.

        Raises:
            RuntimeError: If shared namespace is not activated.
        """
        if self.shared_namespace is None:
            raise RuntimeError("Shared namespace not activated")

        namespaced_topic = self._get_shared_namespaced_topic(topic)
        logging.debug(f"[Messaging] Subscribing client {client.id} to shared topic {namespaced_topic}")

        if namespaced_topic not in self.shared_subscribers:
            self.shared_subscribers[namespaced_topic] = set()
        self.shared_subscribers[namespaced_topic].add(client.id)

        handler = self._make_shared_client_handler(client)
        self.backend.subscribe(namespaced_topic, handler, client_id=client.id, namespace=self.shared_namespace)

    def unsubscribe_shared(self, topic: str, client: Client) -> None:
        """
        Unsubscribe a client from a topic in the shared namespace.

        Args:
            topic: The topic to unsubscribe from.
            client: The client instance to unsubscribe.
        """
        if self.shared_namespace is None:
            return

        namespaced_topic = self._get_shared_namespaced_topic(topic)
        if namespaced_topic in self.shared_subscribers:
            self.shared_subscribers[namespaced_topic].discard(client.id)
            if not self.shared_subscribers[namespaced_topic]:
                self.shared_subscribers.pop(namespaced_topic, None)
        self.backend.unsubscribe(namespaced_topic, client_id=client.id)
