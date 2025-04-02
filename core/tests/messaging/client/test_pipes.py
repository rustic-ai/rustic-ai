import logging
import time
from typing import List, Tuple

import pytest

from rustic_ai.core.messaging.client.pipes import (
    FilteringClient,
    LoggingClient,
    Pipeable,
    ThrottlingClient,
    TransformingClient,
)
from rustic_ai.core.messaging.client.simple_client import SimpleClient
from rustic_ai.core.messaging.core.client import Client
from rustic_ai.core.messaging.core.message import AgentTag, Message, MessageConstants
from rustic_ai.core.utils.gemstone_id import GemstoneGenerator
from rustic_ai.core.utils.priority import Priority


class TestPipes:
    @pytest.fixture
    def gemstone_generator(self):
        """Fixture that returns a GemstoneGenerator instance with a seed of 1."""
        return GemstoneGenerator(1)

    @pytest.fixture
    def sample_message(self, gemstone_generator):
        """Fixture that returns a sample Message instance."""
        return Message(
            topics="test_topic",
            sender=AgentTag(id="testSenderId", name="testSender"),
            format=MessageConstants.RAW_JSON_FORMAT,
            payload={"content": "Test content"},
            id_obj=gemstone_generator.get_id(Priority.NORMAL),
        )

    @pytest.fixture
    def simple_client(self) -> Tuple[Client, List[Message]]:
        messages_received: List[Message] = []

        def message_handler(message: Message):
            messages_received.append(message)

        client = SimpleClient("client1", "Simple Client", message_handler)
        return client, messages_received

    def test_logging_client(self, sample_message, caplog):
        """Test that the LoggingClient logs incoming messages."""
        caplog.set_level(logging.INFO)
        client = LoggingClient()
        client.notify_new_message(sample_message)
        assert sample_message.to_json() in caplog.text

    def test_filtering_client(self, simple_client, gemstone_generator):
        """Test that the FilteringClient filters incoming messages."""
        handling_client, messages_received = simple_client

        m1 = Message(
            topics="topic1",
            sender=AgentTag(id="sender1", name="sender1"),
            format=MessageConstants.RAW_JSON_FORMAT,
            payload={"data": "test"},
            id_obj=gemstone_generator.get_id(Priority.NORMAL),
        )
        m2 = Message(
            topics="topic1",
            sender=AgentTag(id="sender2", name="sender2"),
            format=MessageConstants.RAW_JSON_FORMAT,
            payload={"data": "test"},
            id_obj=gemstone_generator.get_id(Priority.NORMAL),
        )
        m3 = Message(
            topics="topic1",
            sender=AgentTag(id="sender2", name="sender2"),
            format=MessageConstants.RAW_JSON_FORMAT,
            payload={"data": "test"},
            id_obj=gemstone_generator.get_id(Priority.NORMAL),
        )
        m4 = Message(
            topics="topic1",
            sender=AgentTag(id="sender3", name="sender3"),
            format=MessageConstants.RAW_JSON_FORMAT,
            payload={"data": "test"},
            id_obj=gemstone_generator.get_id(Priority.HIGH),
        )

        filter = FilteringClient(lambda m: m.sender.name == "sender2")
        client = filter | handling_client

        client.notify_new_message(m1)
        client.notify_new_message(m2)
        client.notify_new_message(m3)
        client.notify_new_message(m4)

        assert len(messages_received) == 2
        assert m2 in messages_received
        assert m3 in messages_received

    def test_transforming_client(self, simple_client, gemstone_generator):
        """Test that the TransformingClient transforms incoming messages."""
        handling_client, messages_received = simple_client

        m1 = Message(
            topics="topic1",
            sender=AgentTag(id="sender1", name="sender1"),
            format=MessageConstants.RAW_JSON_FORMAT,
            payload={"data": "test"},
            id_obj=gemstone_generator.get_id(Priority.NORMAL),
        )

        def transform_func(message):
            message.payload["content"] = "Transformed content"
            return message

        client = TransformingClient(transform_func) | LoggingClient(log_level=logging.DEBUG) | handling_client
        client.notify_new_message(m1)

        assert messages_received[0].payload["content"] == "Transformed content"

    def test_throttling_client(self, sample_message):
        """Test that the ThrottlingClient adds a delay between incoming messages."""
        delay = 0.5
        throttle = ThrottlingClient(delay)
        client = throttle | LoggingClient(log_level=logging.DEBUG)  # Connect to a LoggingClient for testing

        start_time = time.time()
        client.notify_new_message(sample_message)
        end_time = time.time()

        assert (end_time - start_time) >= delay

    def test_pipeline(self, simple_client, gemstone_generator):
        """Test a pipeline of multiple clients."""
        handling_client, messages_received = simple_client

        m1 = Message(
            topics="topic1",
            sender=AgentTag(id="sender1", name="sender1"),
            format=MessageConstants.RAW_JSON_FORMAT,
            payload={"data": "test"},
            id_obj=gemstone_generator.get_id(Priority.NORMAL),
        )
        m2 = Message(
            topics="topic1",
            sender=AgentTag(id="sender2", name="sender2"),
            format=MessageConstants.RAW_JSON_FORMAT,
            payload={"data": "test"},
            id_obj=gemstone_generator.get_id(Priority.NORMAL),
        )
        m3 = Message(
            topics="topic1",
            sender=AgentTag(id="sender2", name="sender2"),
            format=MessageConstants.RAW_JSON_FORMAT,
            payload={"data": "test"},
            id_obj=gemstone_generator.get_id(Priority.NORMAL),
        )
        m4 = Message(
            topics="topic1",
            sender=AgentTag(id="sender3", name="sender3"),
            format=MessageConstants.RAW_JSON_FORMAT,
            payload={"data": "test"},
            id_obj=gemstone_generator.get_id(Priority.HIGH),
        )

        def filter_func(message: Message):
            return message.priority == Priority.HIGH

        def transform_func(message):
            message.payload["content"] = "Transformed content"
            return message

        filter_client = FilteringClient(filter_func)
        transform_client = TransformingClient(transform_func)
        throttle_client = ThrottlingClient(0.5)

        client = filter_client | transform_client | throttle_client | handling_client  # type: ignore

        start_time = time.time()
        client.notify_new_message(m1)
        client.notify_new_message(m2)
        client.notify_new_message(m3)
        client.notify_new_message(m4)
        end_time = time.time()

        assert len(messages_received) == 1
        assert messages_received[0].id == m4.id
        assert messages_received[0].payload["content"] == "Transformed content"
        assert (end_time - start_time) >= 0.5

    # Test Pipeable subclass should also extend Client
    def test_pipeable_subclass(self):
        """Test that a Pipeable subclass also extends Client."""

        with pytest.raises(TypeError):

            class TestPipeable(Pipeable):
                def __init__(self):
                    super().__init__()

    # Test client can be piped to a non client object
    def test_pipe_to_non_client(self, simple_client):
        """Test that a client can be piped to a non-client object."""

        def transform_func(message):
            message.payload["content"] = "Transformed content"
            return message

        with pytest.raises(TypeError):
            TransformingClient(transform_func) | "test"  # type: ignore
