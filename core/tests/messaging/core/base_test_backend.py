from abc import ABC
import time
from typing import List

import pytest

from rustic_ai.core.messaging.core.message import (
    AgentTag,
    Message,
    MessageConstants,
    Priority,
)
from rustic_ai.core.messaging.core.messaging_backend import MessagingBackend
from rustic_ai.core.utils.gemstone_id import GemstoneGenerator


class BaseTestBackendABC(ABC):
    @pytest.fixture
    def generator(self):
        """
        Fixture that returns a GemstoneGenerator instance with a seed of 1.
        """
        return GemstoneGenerator(1)

    @pytest.fixture
    def backend(self):
        """
        Fixture that returns an instance of the backend implementation being tested.
        This should be overridden in subclasses that test specific backend implementations.
        """
        raise NotImplementedError("This fixture should be overridden in subclasses.")

    @pytest.fixture
    def topic(self) -> str:
        return "test_topic"

    def test_store_message(self, backend: MessagingBackend, generator: GemstoneGenerator, topic: str, request):
        """
        Test adding a message to a topic.
        """
        message = Message(
            topics=topic,
            sender=AgentTag(id="senderId", name="sender"),
            format=MessageConstants.RAW_JSON_FORMAT,
            payload={"key": "value"},
            id_obj=generator.get_id(Priority.NORMAL),
        )
        namespace = request.node.name
        backend.store_message(namespace, topic, message)
        messages = backend.get_messages_for_topic(topic)
        assert len(messages) == 1
        assert messages[0].payload == {"key": "value"}

    def test_message_ordering_by_priority(
        self, backend: MessagingBackend, generator: GemstoneGenerator, topic: str, request
    ):
        """
        Test that messages are ordered first by priority and then by ID.
        """
        id1 = generator.get_id(Priority.NORMAL)
        id2 = generator.get_id(Priority.HIGH)
        time.sleep(0.001)
        id3 = generator.get_id(Priority.LOW)
        id4 = generator.get_id(Priority.NORMAL)
        id5 = generator.get_id(Priority.URGENT)
        id6 = generator.get_id(Priority.LOW)

        sender = AgentTag(id="senderId", name="sender")

        m1 = Message(
            topics=topic,
            sender=sender,
            format=MessageConstants.RAW_JSON_FORMAT,
            payload={"key": "m1"},
            id_obj=id1,
        )
        m2 = Message(
            topics=topic,
            sender=sender,
            format=MessageConstants.RAW_JSON_FORMAT,
            payload={"key": "m2"},
            id_obj=id2,
        )
        m3 = Message(
            topics=topic,
            sender=sender,
            format=MessageConstants.RAW_JSON_FORMAT,
            payload={"key": "m3"},
            id_obj=id3,
        )
        m4 = Message(
            topics=topic,
            sender=sender,
            format=MessageConstants.RAW_JSON_FORMAT,
            payload={"key": "m4"},
            id_obj=id4,
        )
        m5 = Message(
            topics=topic,
            sender=sender,
            format=MessageConstants.RAW_JSON_FORMAT,
            payload={"key": "m5"},
            id_obj=id5,
        )
        m6 = Message(
            topics=topic,
            sender=sender,
            format=MessageConstants.RAW_JSON_FORMAT,
            payload={"key": "m6"},
            id_obj=id6,
        )

        namespace = request.node.name
        # Add messages to the topic
        backend.store_message(namespace, topic, m1)
        backend.store_message(namespace, topic, m2)
        backend.store_message(namespace, topic, m3)
        backend.store_message(namespace, topic, m4)
        backend.store_message(namespace, topic, m5)
        backend.store_message(namespace, topic, m6)

        # Retrieve messages for the topic
        retrieved_messages = backend.get_messages_for_topic(topic)

        # Check the order of the retrieved messages
        assert retrieved_messages == [m5, m2, m1, m4, m3, m6]

    def test_load_subscribers(self, backend: MessagingBackend):
        """
        Test loading subscribers from the backend backend.
        """
        subscribers = backend.load_subscribers("namespace")
        assert isinstance(subscribers, dict)
        # Further assertions can be added based on the expected subscribers in the backend.

    # Test method to get messages since a given message ID
    def test_get_messages_for_topic_since(
        self, backend: MessagingBackend, generator: GemstoneGenerator, topic: str, request
    ):
        """
        Test retrieving messages for a topic since a given message ID.
        """
        id1 = generator.get_id(Priority.NORMAL)
        time.sleep(0.001)
        id2 = generator.get_id(Priority.NORMAL)
        id3 = generator.get_id(Priority.NORMAL)
        time.sleep(0.001)
        id4 = generator.get_id(Priority.NORMAL)
        id5 = generator.get_id(Priority.NORMAL)
        id6 = generator.get_id(Priority.NORMAL)

        sender = AgentTag(id="senderId", name="sender")

        m1 = Message(
            topics=topic,
            sender=sender,
            format=MessageConstants.RAW_JSON_FORMAT,
            payload={"key": "m1"},
            id_obj=id1,
        )
        m2 = Message(
            topics=topic,
            sender=sender,
            format=MessageConstants.RAW_JSON_FORMAT,
            payload={"key": "m2"},
            id_obj=id2,
        )
        m3 = Message(
            topics=topic,
            sender=sender,
            format=MessageConstants.RAW_JSON_FORMAT,
            payload={"key": "m3"},
            id_obj=id3,
        )
        m4 = Message(
            topics=topic,
            sender=sender,
            format=MessageConstants.RAW_JSON_FORMAT,
            payload={"key": "m4"},
            id_obj=id4,
        )
        m5 = Message(
            topics=topic,
            sender=sender,
            format=MessageConstants.RAW_JSON_FORMAT,
            payload={"key": "m5"},
            id_obj=id5,
        )
        m6 = Message(
            topics=topic,
            sender=sender,
            format=MessageConstants.RAW_JSON_FORMAT,
            payload={"key": "m6"},
            id_obj=id6,
        )

        namespace = request.node.name
        # Add messages to the topic
        backend.store_message(namespace, topic, m1)
        backend.store_message(namespace, topic, m2)
        backend.store_message(namespace, topic, m3)
        backend.store_message(namespace, topic, m4)
        backend.store_message(namespace, topic, m5)
        backend.store_message(namespace, topic, m6)

        # Retrieve messages for the topic since a given message ID
        retrieved_messages = backend.get_messages_for_topic_since(topic, id3.to_int())

        # Check the order of the retrieved messages
        assert retrieved_messages == [m4, m5, m6]

    # Test method to get the next message since a given message ID
    def test_get_next_message_for_topic_since(
        self, backend: MessagingBackend, generator: GemstoneGenerator, topic: str, request
    ):
        """
        Test retrieving the next message for a topic since a given message ID.
        """
        id1 = generator.get_id(Priority.NORMAL)
        id2 = generator.get_id(Priority.NORMAL)
        time.sleep(0.001)
        id3 = generator.get_id(Priority.NORMAL)
        time.sleep(0.001)
        id4 = generator.get_id(Priority.NORMAL)
        id5 = generator.get_id(Priority.NORMAL)
        time.sleep(0.001)
        id6 = generator.get_id(Priority.NORMAL)

        sender = AgentTag(id="senderId", name="sender")

        m1 = Message(
            topics=topic,
            sender=sender,
            format=MessageConstants.RAW_JSON_FORMAT,
            payload={"key": "m1"},
            id_obj=id1,
        )
        m2 = Message(
            topics=topic,
            sender=sender,
            format=MessageConstants.RAW_JSON_FORMAT,
            payload={"key": "m2"},
            id_obj=id2,
        )
        m3 = Message(
            topics=topic,
            sender=sender,
            format=MessageConstants.RAW_JSON_FORMAT,
            payload={"key": "m3"},
            id_obj=id3,
        )
        m4 = Message(
            topics=topic,
            sender=sender,
            format=MessageConstants.RAW_JSON_FORMAT,
            payload={"key": "m4"},
            id_obj=id4,
        )
        m5 = Message(
            topics=topic,
            sender=sender,
            format=MessageConstants.RAW_JSON_FORMAT,
            payload={"key": "m5"},
            id_obj=id5,
        )
        m6 = Message(
            topics=topic,
            sender=sender,
            format=MessageConstants.RAW_JSON_FORMAT,
            payload={"key": "m6"},
            id_obj=id6,
        )

        namespace = request.node.name
        # Add messages to the topic
        backend.store_message(namespace, topic, m1)
        backend.store_message(namespace, topic, m2)
        backend.store_message(namespace, topic, m3)
        backend.store_message(namespace, topic, m4)
        backend.store_message(namespace, topic, m5)
        backend.store_message(namespace, topic, m6)

        # Retrieve messages for the topic since a given message ID
        retrieved_message = backend.get_next_message_for_topic_since(topic, id3.to_int())

        # Check the retrieved message
        assert retrieved_message == m4

    # Test method to get messages since a given message ID ensuring newer messages with higher priority are not lost
    def test_get_messages_for_topic_since_with_higher_priority(
        self, backend: MessagingBackend, generator: GemstoneGenerator, topic: str, request
    ):
        """
        Test retrieving messages for a topic since a given message ID ensuring newer messages with higher priority are not lost.
        """
        id1 = generator.get_id(Priority.NORMAL)
        id2 = generator.get_id(Priority.NORMAL)
        id3 = generator.get_id(Priority.NORMAL)
        time.sleep(0.001)
        id4 = generator.get_id(Priority.NORMAL)
        time.sleep(0.001)
        id5 = generator.get_id(Priority.NORMAL)
        id6 = generator.get_id(Priority.NORMAL)
        time.sleep(0.001)
        id7 = generator.get_id(Priority.HIGH)
        id8 = generator.get_id(Priority.URGENT)

        sender = AgentTag(id="senderId", name="sender")

        m1 = Message(
            topics=topic,
            sender=sender,
            format=MessageConstants.RAW_JSON_FORMAT,
            payload={"key": "m1"},
            id_obj=id1,
        )
        m2 = Message(
            topics=topic,
            sender=sender,
            format=MessageConstants.RAW_JSON_FORMAT,
            payload={"key": "m2"},
            id_obj=id2,
        )
        m3 = Message(
            topics=topic,
            sender=sender,
            format=MessageConstants.RAW_JSON_FORMAT,
            payload={"key": "m3"},
            id_obj=id3,
        )
        m4 = Message(
            topics=topic,
            sender=sender,
            format=MessageConstants.RAW_JSON_FORMAT,
            payload={"key": "m4"},
            id_obj=id4,
        )
        m5 = Message(
            topics=topic,
            sender=sender,
            format=MessageConstants.RAW_JSON_FORMAT,
            payload={"key": "m5"},
            id_obj=id5,
        )
        m6 = Message(
            topics=topic,
            sender=sender,
            format=MessageConstants.RAW_JSON_FORMAT,
            payload={"key": "m6"},
            id_obj=id6,
        )
        m7 = Message(
            topics=topic,
            sender=sender,
            format=MessageConstants.RAW_JSON_FORMAT,
            payload={"key": "m7"},
            id_obj=id7,
        )
        m8 = Message(
            topics=topic,
            sender=sender,
            format=MessageConstants.RAW_JSON_FORMAT,
            payload={"key": "m8"},
            id_obj=id8,
        )

        namespace = request.node.name
        # Add messages to the topic
        backend.store_message(namespace, topic, m1)
        backend.store_message(namespace, topic, m2)
        backend.store_message(namespace, topic, m3)
        backend.store_message(namespace, topic, m4)
        backend.store_message(namespace, topic, m5)
        backend.store_message(namespace, topic, m6)
        backend.store_message(namespace, topic, m7)
        backend.store_message(namespace, topic, m8)

        # Retrieve messages for the topic since a given message ID
        retrieved_messages = backend.get_messages_for_topic_since(topic, id3.to_int())

        # Check the order of the retrieved messages
        assert retrieved_messages == [m8, m7, m4, m5, m6]

    # Test subscription on a topic
    def test_subscribe(self, backend: MessagingBackend, generator: GemstoneGenerator, topic: str, request):
        """
        Test subscribing to a topic.
        """
        messages: List[Message] = []

        id1 = generator.get_id(Priority.NORMAL)

        def callback(message: Message):
            messages.append(message)

        backend.subscribe(topic, callback)
        namespace = request.node.name

        m1 = Message(
            topics=topic,
            sender=AgentTag(id="senderId", name="sender"),
            format=MessageConstants.RAW_JSON_FORMAT,
            payload={"key": "m1"},
            id_obj=id1,
        )

        backend.store_message(namespace, topic, m1)

        time.sleep(0.001)

        assert len(messages) == 1

        backend.unsubscribe(topic)

        m2 = Message(
            topics=topic,
            sender=AgentTag(id="senderId", name="sender"),
            format=MessageConstants.RAW_JSON_FORMAT,
            payload={"key": "m2"},
            id_obj=generator.get_id(Priority.NORMAL),
        )

        backend.store_message(namespace, topic, m2)

        time.sleep(0.001)

        assert len(messages) == 1

    def test_get_messages_by_id(self, backend: MessagingBackend, generator: GemstoneGenerator, topic: str, request):
        """
        Test retrieving messages by their IDs.
        """
        id1 = generator.get_id(Priority.NORMAL)
        id2 = generator.get_id(Priority.HIGH)
        id3 = generator.get_id(Priority.LOW)

        sender = AgentTag(id="senderId", name="sender")

        m1 = Message(
            topics=topic,
            sender=sender,
            format=MessageConstants.RAW_JSON_FORMAT,
            payload={"key": "m1"},
            id_obj=id1,
        )
        m2 = Message(
            topics=topic,
            sender=sender,
            format=MessageConstants.RAW_JSON_FORMAT,
            payload={"key": "m2"},
            id_obj=id2,
        )
        m3 = Message(
            topics=topic,
            sender=sender,
            format=MessageConstants.RAW_JSON_FORMAT,
            payload={"key": "m3"},
            id_obj=id3,
        )

        namespace = request.node.name

        # Add messages to the topic
        backend.store_message(namespace, topic, m1)
        backend.store_message(namespace, topic, m2)
        backend.store_message(namespace, topic, m3)

        # Retrieve messages by their IDs
        msg_ids = [id1.to_int(), id3.to_int()]
        retrieved_messages = backend.get_messages_by_id(namespace, msg_ids)

        # Check that only requested messages are retrieved
        assert len(retrieved_messages) == 2
        assert retrieved_messages[0] == m1
        assert retrieved_messages[1] == m3
