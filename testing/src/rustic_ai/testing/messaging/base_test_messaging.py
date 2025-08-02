from abc import ABC, abstractmethod
import time
from typing import List, Tuple, Union

import pytest

from rustic_ai.core.messaging.client import SimpleClient
from rustic_ai.core.messaging.core import Client, Message, MessagingInterface
from rustic_ai.core.messaging.core.message import (
    AgentTag,
    MessageConstants,
    ProcessEntry,
)
from rustic_ai.core.messaging.core.messaging_config import MessagingConfig
from rustic_ai.core.utils.gemstone_id import GemstoneGenerator
from rustic_ai.core.utils.priority import Priority


class BaseTestMessagingABC(ABC):
    @pytest.fixture
    @abstractmethod
    def messaging_config(self) -> MessagingConfig:
        """
        Fixture that returns an instance of the storage implementation being tested.
        This should be overridden in subclasses that test specific storage implementations.
        """
        raise NotImplementedError("This fixture should be overridden in subclasses.")

    @pytest.fixture
    @abstractmethod
    def namespace(self):
        """
        Fixture that returns the namespace for the messaging interface.
        """
        raise NotImplementedError("This fixture should be overridden in subclasses.")

    @pytest.fixture
    def generator(self):
        """
        Fixture that returns a GemstoneGenerator instance with a seed of 1.
        """
        return GemstoneGenerator(1)

    @pytest.fixture
    def messaging(self, namespace, messaging_config):
        """
        Fixture that returns an instance of the Messaging Interface initialized with the given storage.
        """
        mbus = MessagingInterface(namespace, messaging_config)
        yield mbus
        mbus.shutdown()

    @pytest.fixture
    def alt_messaging(self, namespace, messaging_config):
        """
        Fixture that returns an instance of the Messaging Interface initialized with the given storage.
        """
        mbus = MessagingInterface(f"{namespace}_alt", messaging_config)
        yield mbus
        mbus.shutdown()

    @pytest.fixture
    def simple_client(self) -> Tuple[Client, List[Message]]:
        messages_received: List[Message] = []

        def message_handler(message: Message):
            messages_received.append(message)

        client = SimpleClient("client1", "Simple Client", message_handler)
        return client, messages_received

    @pytest.fixture
    def simple_client_2(self) -> Tuple[Client, List[Message]]:
        messages_received: List[Message] = []

        def message_handler(message: Message):
            messages_received.append(message)

        client = SimpleClient("client2", "Simple Client", message_handler)
        return client, messages_received

    # A pytest fixure for a simple client that can send messages to the message bus
    @pytest.fixture
    def message_publisher(self) -> Tuple[Client, List[Message]]:
        messages_received: List[Message] = []

        class TestClient(SimpleClient):
            def __init__(self, client_id: str, name: str):
                super().__init__(client_id, name, self._handle_message)

            def _handle_message(self, message: Message):
                messages_received.append(message)

            def send_message(
                self,
                topic: Union[str, List[str]],
                format: str,
                payload: dict,
                message_id,
                message_history: List[ProcessEntry] = [],
                enrich_with_history: int = 0,
            ):
                message = Message(
                    topics=topic,
                    sender=AgentTag(id=self.id, name=self.name),
                    format=format,
                    payload=payload,
                    id_obj=message_id,
                    message_history=message_history,
                    enrich_with_history=enrich_with_history,
                )
                self.publish(message)
                return message

        return TestClient("sender1", "Simple Publishing Client"), messages_received

    def test_register_unregister_client(self, messaging, simple_client):
        """
        Test registering and unregistering a client.
        """
        client, _ = simple_client
        messaging.register_client(client)
        assert "client1" in messaging.clients

        messaging.unregister_client(client)
        assert "client1" not in messaging.clients

    def test_publish_and_subscribe(self, messaging, message_publisher, simple_client, generator):
        """
        Test publishing a message and subscribing a client to a topic.
        """
        client, messages_received = simple_client
        messaging.register_client(client)
        messaging.subscribe("topic1", client)

        sender, sender_messages_received = message_publisher
        messaging.register_client(sender)
        messaging.subscribe("topic1", sender)

        message_id = generator.get_id(Priority.NORMAL)
        sender.send_message("topic1", MessageConstants.RAW_JSON_FORMAT, {"data": "value"}, message_id)

        time.sleep(0.01)  # Give the message time to be processed

        assert len(messages_received) == 1
        assert messages_received[0].payload == {"data": "value"}
        assert messages_received[0].id == message_id.to_int()

        assert len(sender_messages_received) == 0

    def test_publish_and_subscribe_multiple_topics(self, messaging, message_publisher, simple_client, generator):
        """
        Test publishing a message and subscribing a client to multiple topics.
        """
        client, messages_received = simple_client
        messaging.register_client(client)
        messaging.subscribe("topic1", client)
        messaging.subscribe("topic2", client)

        sender, _ = message_publisher
        messaging.register_client(sender)

        message_id1 = generator.get_id(Priority.NORMAL)
        sender.send_message(
            ["topic1", "topic2"],
            MessageConstants.RAW_JSON_FORMAT,
            {"data": "value1"},
            message_id1,
        )

        time.sleep(0.01)
        assert len(messages_received) == 2

        assert messages_received[0].payload == {"data": "value1"}
        assert messages_received[0].id == message_id1.to_int()

        assert messages_received[1].payload == {"data": "value1"}
        assert messages_received[1].id == message_id1.to_int()

        topics = [message.topic_published_to for message in messages_received]

        assert "topic1" in topics
        assert "topic2" in topics

    def test_unsubscribe(self, messaging, message_publisher, simple_client, generator):
        """
        Test unsubscribing a client from a topic.
        """
        client, messages_received = simple_client
        messaging.register_client(client)
        messaging.subscribe("topic1", client)
        messaging.unsubscribe("topic1", client)

        sender, _ = message_publisher
        messaging.register_client(sender)
        messaging.subscribe("topic1", sender)

        message_id = generator.get_id(Priority.NORMAL)
        sender.send_message("topic1", MessageConstants.RAW_JSON_FORMAT, {"data": "value"}, message_id)

        # Since client1 is unsubscribed, it should not receive the message
        assert not messages_received

    def test_multiple_subscribers_to_topic(
        self, message_publisher, simple_client, simple_client_2, messaging, generator
    ):
        """
        Test that multiple subscribers to a topic all receive the published message.
        """
        client1, messages_received1 = simple_client
        client2, messages_received2 = simple_client_2

        messaging.register_client(client1)
        messaging.register_client(client2)

        messaging.subscribe("topic1", client1)
        messaging.subscribe("topic1", client2)

        sender, _ = message_publisher
        messaging.register_client(sender)
        messaging.subscribe("topic1", sender)

        message_id = generator.get_id(Priority.NORMAL)
        sender.send_message("topic1", MessageConstants.RAW_JSON_FORMAT, {"data": "value"}, message_id)

        time.sleep(0.01)  # Give the message time to be processed

        assert len(messages_received1) == 1
        assert len(messages_received2) == 1

    def test_multiple_topics_subscription(self, message_publisher, messaging, simple_client, generator):
        """
        Test that a client subscribed to multiple topics receives messages for each topic.
        """
        client, messages_received = simple_client
        messaging.register_client(client)
        messaging.subscribe("topic1", client)
        messaging.subscribe("topic2", client)

        sender, _ = message_publisher
        messaging.register_client(sender)
        messaging.subscribe("topic1", sender)
        messaging.subscribe("topic2", sender)

        message_id1 = generator.get_id(Priority.NORMAL)
        message_id2 = generator.get_id(Priority.NORMAL)

        sender.send_message("topic1", MessageConstants.RAW_JSON_FORMAT, {"data": "value1"}, message_id1)
        sender.send_message("topic2", MessageConstants.RAW_JSON_FORMAT, {"data": "value2"}, message_id2)

        time.sleep(0.01)  # Give the message time to be processed

        assert len(messages_received) == 2
        assert messages_received[0].payload == {"data": "value1"}
        assert messages_received[1].payload == {"data": "value2"}

    def test_message_retrieval_since_id(self, message_publisher, messaging, simple_client, generator):
        """
        Test retrieving messages for a topic since a specific message ID.
        """
        client, _ = simple_client
        messaging.register_client(client)
        messaging.subscribe("topic1", client)

        sender, _ = message_publisher
        messaging.register_client(sender)
        messaging.subscribe("topic1", sender)

        old_id = generator.get_id(Priority.NORMAL)
        time.sleep(0.001)
        new_id = generator.get_id(Priority.NORMAL)

        sender.send_message("topic1", MessageConstants.RAW_JSON_FORMAT, {"data": "old_value"}, old_id)
        sender.send_message("topic1", MessageConstants.RAW_JSON_FORMAT, {"data": "new_value"}, new_id)

        messages = messaging.get_messages_for_topic_since("topic1", old_id.to_int())
        assert len(messages) == 1
        assert messages[0].payload == {"data": "new_value"}

    def test_unsubscribe_non_subscribed_client(self, messaging, simple_client):
        """
        Test unsubscribing a client that isn't subscribed to a topic.
        """
        client, _ = simple_client
        messaging.register_client(client)
        # This should not raise an error
        messaging.unsubscribe("topic1", client)

    def test_register_already_registered_client(self, messaging, simple_client):
        """
        Test registering a client that's already registered.
        """
        client, _ = simple_client
        messaging.register_client(client)
        # Registering the same client again should not raise an error
        messaging.register_client(client)

    def test_unregister_non_registered_client(self, messaging, simple_client):
        """
        Test unregistering a client that isn't registered.
        """
        client, _ = simple_client
        # This should not raise an error
        messaging.unregister_client(client)

    # Test get_messages method
    def test_get_messages(self, message_publisher, messaging, simple_client, generator):
        """
        Test retrieving all messages for a topic.
        """
        client, _ = simple_client
        messaging.register_client(client)
        messaging.subscribe("topic1", client)

        sender, _ = message_publisher
        messaging.register_client(sender)
        messaging.subscribe("topic1", sender)

        sender.send_message(
            "topic1",
            MessageConstants.RAW_JSON_FORMAT,
            {"data": "value1"},
            generator.get_id(Priority.NORMAL),
        )
        sender.send_message(
            "topic1",
            MessageConstants.RAW_JSON_FORMAT,
            {"data": "value2"},
            generator.get_id(Priority.NORMAL),
        )

        messages = messaging.get_messages("topic1")
        assert len(messages) == 2
        assert messages[0].payload == {"data": "value1"}
        assert messages[1].payload == {"data": "value2"}

        messages = messaging.get_messages("topic1")
        assert len(messages) == 2
        assert messages[0].payload == {"data": "value1"}
        assert messages[1].payload == {"data": "value2"}

    # Test get_next_message_for_topic method
    def test_get_next_message_for_topic(self, message_publisher, messaging, simple_client, generator):
        """
        Test retrieving the next message for a topic.
        """
        client, _ = simple_client
        messaging.register_client(client)
        messaging.subscribe("topic1", client)

        sender, _ = message_publisher
        messaging.register_client(sender)
        messaging.subscribe("topic1", sender)

        message_id1 = generator.get_id(Priority.NORMAL)
        time.sleep(0.001)
        message_id2 = generator.get_id(Priority.NORMAL)

        sender.send_message("topic1", MessageConstants.RAW_JSON_FORMAT, {"data": "value1"}, message_id1)
        sender.send_message("topic1", MessageConstants.RAW_JSON_FORMAT, {"data": "value2"}, message_id2)

        message = messaging.get_next_message_for_topic("topic1", 0)
        assert message.payload == {"data": "value1"}

        message = messaging.get_next_message_for_topic("topic1", message.id)
        assert message.payload == {"data": "value2"}

    # Test get_next_message_for_client method
    def test_get_next_message_for_client(self, message_publisher, messaging, simple_client, generator):
        """
        Test retrieving the next message for a client.
        """
        client, _ = simple_client
        messaging.register_client(client)
        messaging.subscribe("topic1", client)

        sender, _ = message_publisher
        messaging.register_client(sender)
        messaging.subscribe("topic1", sender)

        message_id1 = generator.get_id(Priority.NORMAL)
        time.sleep(0.001)
        message_id2 = generator.get_id(Priority.NORMAL)

        sender.send_message("topic1", MessageConstants.RAW_JSON_FORMAT, {"data": "value1"}, message_id1)
        sender.send_message("topic1", MessageConstants.RAW_JSON_FORMAT, {"data": "value2"}, message_id2)

        message = messaging.get_next_message_for_client(client.id, 0)
        assert message.payload == {"data": "value1"}

        message = messaging.get_next_message_for_client(client.id, message.id)
        assert message.payload == {"data": "value2"}

    # Test messaging isolation between different namespaces
    def test_messaging_isolation(
        self,
        messaging,
        alt_messaging,
        message_publisher,
        simple_client,
        simple_client_2,
        generator,
    ):
        """
        Test that messages are isolated between different messaging interfaces with different namespaces.
        """
        client, messages_received = simple_client
        messaging.register_client(client)
        messaging.subscribe("topic1", client)

        sender, _ = message_publisher
        messaging.register_client(sender)
        messaging.subscribe("topic1", sender)

        alt_client, alt_messages_received = simple_client_2
        alt_messaging.register_client(alt_client)
        alt_messaging.subscribe("topic1", alt_client)

        message_id = generator.get_id(Priority.NORMAL)
        sender.send_message("topic1", MessageConstants.RAW_JSON_FORMAT, {"data": "value"}, message_id)

        time.sleep(0.01)  # Give the message time to be processed

        assert len(messages_received) == 1
        assert len(alt_messages_received) == 0

    def test_enrich_message(
        self, messaging, alt_messaging, message_publisher, simple_client, simple_client_2, generator
    ):

        topic = "enrich_topic"
        client, messages_received = simple_client
        messaging.register_client(client)
        messaging.subscribe(topic, client)

        sender, _ = message_publisher
        messaging.register_client(sender)
        messaging.subscribe(topic, sender)

        message_id1 = generator.get_id(Priority.NORMAL)
        sender.send_message(topic, MessageConstants.RAW_JSON_FORMAT, {"data": "value"}, message_id1)

        message_id2 = generator.get_id(Priority.NORMAL)
        history = [
            ProcessEntry(
                agent=AgentTag(name="test-sender"),
                origin=message_id1.to_int(),
                result=message_id2.to_int(),
                processor="test_processor",
            )
        ]
        sender.send_message(topic, MessageConstants.RAW_JSON_FORMAT, {"data": "value2"}, message_id2, history)

        message_id3 = generator.get_id(Priority.NORMAL)
        history.append(
            ProcessEntry(
                agent=AgentTag(name="test-sender"),
                origin=message_id2.to_int(),
                result=message_id3.to_int(),
                processor="test_processor",
            )
        )
        sender.send_message(topic, MessageConstants.RAW_JSON_FORMAT, {"data": "value2"}, message_id3, history, 2)

        time.sleep(0.01)  # Give the message time to be processed

        assert len(messages_received) == 3

        prev_msgs = messages_received[2].session_state["enriched_history"]
        assert len(prev_msgs) == 2
        assert Message.from_json(prev_msgs[0]).id == message_id1.to_int()
        assert Message.from_json(prev_msgs[1]).id == message_id2.to_int()
