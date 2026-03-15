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

    # =========================================================================
    # Per-client subscribe tests (client_id parameter)
    # =========================================================================

    def test_subscribe_per_client(
        self, backend: MessagingBackend, generator: GemstoneGenerator, topic: str, request
    ):
        """Smoke test: per-client subscribe delivers messages to the registered handler."""
        messages: List[Message] = []
        namespace = request.node.name

        def callback(message: Message):
            messages.append(message)

        backend.subscribe(topic, callback, client_id="client_A")

        m1 = Message(
            topics=topic,
            sender=AgentTag(id="senderId", name="sender"),
            format=MessageConstants.RAW_JSON_FORMAT,
            payload={"key": "m1"},
            id_obj=generator.get_id(Priority.NORMAL),
        )
        backend.store_message(namespace, topic, m1)
        time.sleep(0.1)

        assert len(messages) == 1
        assert messages[0].payload == {"key": "m1"}

        backend.unsubscribe(topic, client_id="client_A")

    def test_multiple_clients_same_topic(
        self, backend: MessagingBackend, generator: GemstoneGenerator, topic: str, request
    ):
        """Both client_A and client_B receive the same message when subscribed to the same topic."""
        messages_a: List[Message] = []
        messages_b: List[Message] = []
        namespace = request.node.name

        backend.subscribe(topic, lambda m: messages_a.append(m), client_id="client_A")
        backend.subscribe(topic, lambda m: messages_b.append(m), client_id="client_B")

        m1 = Message(
            topics=topic,
            sender=AgentTag(id="senderId", name="sender"),
            format=MessageConstants.RAW_JSON_FORMAT,
            payload={"key": "m1"},
            id_obj=generator.get_id(Priority.NORMAL),
        )
        backend.store_message(namespace, topic, m1)
        time.sleep(0.2)

        assert len(messages_a) == 1, f"client_A expected 1 message, got {len(messages_a)}"
        assert len(messages_b) == 1, f"client_B expected 1 message, got {len(messages_b)}"

        backend.unsubscribe(topic, client_id="client_A")
        backend.unsubscribe(topic, client_id="client_B")

    def test_unsubscribe_per_client(
        self, backend: MessagingBackend, generator: GemstoneGenerator, topic: str, request
    ):
        """After unsubscribing client_A, only client_B receives subsequent messages."""
        messages_a: List[Message] = []
        messages_b: List[Message] = []
        namespace = request.node.name

        backend.subscribe(topic, lambda m: messages_a.append(m), client_id="client_A")
        backend.subscribe(topic, lambda m: messages_b.append(m), client_id="client_B")

        # Unsubscribe client_A
        backend.unsubscribe(topic, client_id="client_A")

        m1 = Message(
            topics=topic,
            sender=AgentTag(id="senderId", name="sender"),
            format=MessageConstants.RAW_JSON_FORMAT,
            payload={"key": "m1"},
            id_obj=generator.get_id(Priority.NORMAL),
        )
        backend.store_message(namespace, topic, m1)
        time.sleep(0.2)

        assert len(messages_a) == 0, "client_A should not receive messages after unsubscribe"
        assert len(messages_b) == 1, "client_B should still receive messages"

        backend.unsubscribe(topic, client_id="client_B")

    def test_per_client_ordered_delivery(
        self, backend: MessagingBackend, generator: GemstoneGenerator, topic: str, request
    ):
        """Messages are delivered in order of ascending message ID."""
        received_ids: List[int] = []
        namespace = request.node.name

        def callback(message: Message):
            received_ids.append(message.id)

        backend.subscribe(topic, callback, client_id="client_A")

        id1 = generator.get_id(Priority.NORMAL)
        time.sleep(0.002)
        id2 = generator.get_id(Priority.NORMAL)
        time.sleep(0.002)
        id3 = generator.get_id(Priority.NORMAL)

        for id_obj, key in [(id1, "m1"), (id2, "m2"), (id3, "m3")]:
            backend.store_message(
                namespace,
                topic,
                Message(
                    topics=topic,
                    sender=AgentTag(id="senderId", name="sender"),
                    format=MessageConstants.RAW_JSON_FORMAT,
                    payload={"key": key},
                    id_obj=id_obj,
                ),
            )

        time.sleep(0.3)

        assert len(received_ids) == 3, f"Expected 3 messages, got {len(received_ids)}"
        assert received_ids == sorted(received_ids), f"Messages not in order: {received_ids}"

        backend.unsubscribe(topic, client_id="client_A")

    def test_per_client_sequential_delivery(
        self, backend: MessagingBackend, generator: GemstoneGenerator, topic: str, request
    ):
        """
        Messages are processed sequentially (one at a time) per client.
        Verified by checking that handler intervals don't overlap: start1, end1, start2, end2, ...
        """
        import threading

        events: List[tuple] = []  # (msg_id, "start"/"end")
        namespace = request.node.name
        event_lock = threading.Lock()

        def slow_handler(message: Message):
            with event_lock:
                events.append((message.id, "start"))
            time.sleep(0.05)  # 50ms processing time
            with event_lock:
                events.append((message.id, "end"))

        backend.subscribe(topic, slow_handler, client_id="client_A")

        id1 = generator.get_id(Priority.NORMAL)
        time.sleep(0.001)
        id2 = generator.get_id(Priority.NORMAL)
        time.sleep(0.001)
        id3 = generator.get_id(Priority.NORMAL)

        for id_obj, key in [(id1, "m1"), (id2, "m2"), (id3, "m3")]:
            backend.store_message(
                namespace,
                topic,
                Message(
                    topics=topic,
                    sender=AgentTag(id="senderId", name="sender"),
                    format=MessageConstants.RAW_JSON_FORMAT,
                    payload={"key": key},
                    id_obj=id_obj,
                ),
            )

        # Wait long enough for sequential processing: 3 × 50ms + buffer
        time.sleep(1.0)

        assert len(events) == 6, f"Expected 6 events (start/end × 3), got {len(events)}: {events}"

        # Verify non-overlapping: for each "start" event, the previous event must be an "end"
        # (or it's the very first event)
        for i, (msg_id, kind) in enumerate(events):
            if kind == "start" and i > 0:
                prev_msg_id, prev_kind = events[i - 1]
                assert prev_kind == "end", (
                    f"Found concurrent processing: event[{i - 1}]={events[i - 1]}, event[{i}]={events[i]}\n"
                    f"Full event log: {events}"
                )

        backend.unsubscribe(topic, client_id="client_A")

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
