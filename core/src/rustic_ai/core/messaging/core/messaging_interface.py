import logging
from typing import Dict, List, Optional

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
            raise ValueError(f"Error initializing storage backend: {e}")
        logging.info(f"Using Backend: {messaging_config}")

        self.clients: Dict[str, Client] = {}
        self.subscribers = self.backend.load_subscribers(namespace)
        self.namespace = namespace

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
            self.backend.store_message(ntopic, message_copy)
            if not self.backend.supports_subscription():  # pragma: no cover
                self._notify_new_message(message_copy.model_copy(deep=True))

    def _notify_new_message(self, message: Message) -> None:
        """
        Notify all subscribers of a new published message.

        Args:
            message (Message): The message instance that was published.
        """
        assert message.topic_published_to is not None
        recipients = self.subscribers.get(self._get_namespaced_topic(message.topic_published_to), set())
        for recipient_id in recipients:
            if recipient_id in self.clients and recipient_id != message.sender.id:  # pragma: no cover
                self.clients[recipient_id].notify_new_message(message)

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
            self._backend_subscribe(namespaced_topic)
        self.subscribers[namespaced_topic].add(client.id)

    def _backend_subscribe(self, topic: str) -> None:
        """
        Subscribe a topic to the storage backend.

        Args:
            topic (str): The topic to subscribe to.
        """
        self.backend.subscribe(self._get_namespaced_topic(topic), self._backend_subscription_handler)

    def _backend_subscription_handler(self, message: Message) -> None:
        """
        Handle new messages from the storage backend.

        Args:
            message (Message): The message instance that was published.
        """
        self._notify_new_message(message)

    def _backend_unsubscribe(self, topic: str) -> None:
        """
        Unsubscribe a topic from the storage backend.

        Args:
            topic (str): The topic to unsubscribe from.
        """
        self.backend.unsubscribe(self._get_namespaced_topic(topic))

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
                self._backend_unsubscribe(namespaced_topic)
                self.subscribers.pop(namespaced_topic, None)

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
            client.disconnect()
        self.backend.cleanup()
        self.clients = {}
        self.subscribers = {}
