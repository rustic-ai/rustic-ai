from abc import ABC
import time
from typing import List
from uuid import uuid4

import pytest

from rustic_ai.core.messaging.core.message import (
    AgentTag,
    Message,
    MessageConstants,
    Priority,
)
from rustic_ai.core.messaging.core.messaging_backend import MessagingBackend
from rustic_ai.core.utils.gemstone_id import EPOCH, GemstoneGenerator, GemstoneID


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
    def test_get_messages_for_topic_since_with_higher_priority(self, backend: MessagingBackend, request):
        """
        Verify the Redis/NATS contract for a guild's default topic at a
        priority-inverted timestamp boundary.
        """
        base_timestamp = EPOCH + 1_000_000
        boundary = GemstoneID(Priority.NORMAL, base_timestamp, 1, 0)
        same_millisecond = GemstoneID(Priority.NORMAL, base_timestamp, 1, 1)
        later_normal = GemstoneID(Priority.NORMAL, base_timestamp + 1, 1, 0)
        later_high = GemstoneID(Priority.HIGH, base_timestamp + 2, 1, 0)
        later_urgent = GemstoneID(Priority.URGENT, base_timestamp + 3, 1, 0)

        assert later_high.to_int() < boundary.to_int()
        assert later_urgent.to_int() < boundary.to_int()

        namespace = f"guild_{request.node.name}_{uuid4().hex}"
        topic = f"{namespace}:default_topic"
        sender = AgentTag(id="senderId", name="sender")

        def make_message(label: str, id_obj: GemstoneID) -> Message:
            return Message(
                topics="default_topic",
                sender=sender,
                format=MessageConstants.RAW_JSON_FORMAT,
                payload={"label": label},
                id_obj=id_obj,
                topic_published_to="default_topic",
            )

        fixtures = [
            make_message("boundary", boundary),
            make_message("same_millisecond", same_millisecond),
            make_message("later_normal", later_normal),
            make_message("later_high", later_high),
            make_message("later_urgent", later_urgent),
        ]
        for message in fixtures:
            backend.store_message(namespace, topic, message)

        retrieved_messages = backend.get_messages_for_topic_since(topic, boundary.to_int())
        actual_ids = [message.id for message in retrieved_messages]
        expected_ids = [
            later_urgent.to_int(),
            later_high.to_int(),
            later_normal.to_int(),
        ]
        returned_details = [
            (
                f"{message.payload['label']}"
                f"(priority={int(message.priority)},"
                f"timestamp={int(message.timestamp)},id={message.id})"
            )
            for message in retrieved_messages
        ]
        assert actual_ids == expected_ids, (
            f"cursor={boundary.to_int()}"
            f"(priority={boundary.priority},timestamp={boundary.timestamp}), "
            f"returned={returned_details}"
        )
        assert all(message.topic_published_to == "default_topic" for message in retrieved_messages)

        history = backend.get_messages_for_topic(topic)
        assert [message.id for message in history] == [
            later_urgent.to_int(),
            later_high.to_int(),
            boundary.to_int(),
            same_millisecond.to_int(),
            later_normal.to_int(),
        ]

        by_id = backend.get_messages_by_id(
            namespace,
            [later_high.to_int(), 999999999, boundary.to_int()],
        )
        assert [message.id for message in by_id] == [
            later_high.to_int(),
            boundary.to_int(),
        ]

        other_namespace = f"{namespace}_other"
        other_topic = f"{other_namespace}:default_topic"
        backend.store_message(
            other_namespace,
            other_topic,
            make_message("other_guild", later_normal),
        )
        assert len(backend.get_messages_for_topic(topic)) == len(fixtures)

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

        time.sleep(0.1)

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

        time.sleep(0.1)

        assert len(messages) == 1

    # =========================================================================
    # Per-client subscribe tests (client_id parameter)
    # =========================================================================

    def test_subscribe_per_client(self, backend: MessagingBackend, generator: GemstoneGenerator, topic: str, request):
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

    def test_unsubscribe_per_client(self, backend: MessagingBackend, generator: GemstoneGenerator, topic: str, request):
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
        Verified by checking that handler intervals don't overlap.
        """
        import threading

        events: List[tuple] = []
        namespace = request.node.name
        event_lock = threading.Lock()

        def slow_handler(message: Message):
            with event_lock:
                events.append((message.id, "start"))
            time.sleep(0.05)
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

        time.sleep(1.0)

        assert len(events) == 6, f"Expected 6 events, got {len(events)}: {events}"

        for i, (msg_id, kind) in enumerate(events):
            if kind == "start" and i > 0:
                prev_msg_id, prev_kind = events[i - 1]
                assert (
                    prev_kind == "end"
                ), f"Found concurrent processing: event[{i - 1}]={events[i - 1]}, event[{i}]={events[i]}"

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
