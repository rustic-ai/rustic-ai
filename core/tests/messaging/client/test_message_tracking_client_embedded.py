import time

import pytest

from rustic_ai.core.messaging.client.message_tracking_client import (
    MessageTrackingClient,
)
from rustic_ai.core.messaging.core import Message, MessagingInterface
from rustic_ai.core.messaging.core.message import AgentTag
from rustic_ai.core.messaging.core.messaging_config import MessagingConfig
from rustic_ai.core.utils.gemstone_id import GemstoneGenerator
from rustic_ai.core.utils.priority import Priority


class TestMessageTrackingClientWithEmbedded:
    """Test MessageTrackingClient with EmbeddedMessagingBackend.

    This tests the message tracking functionality with the event-driven
    EmbeddedMessagingBackend to ensure reliable real-time message delivery.
    """

    @pytest.fixture
    def messaging_config(self):
        return MessagingConfig(
            backend_module="rustic_ai.core.messaging.backend.embedded_backend",
            backend_class="EmbeddedMessagingBackend",
            backend_config={"auto_start_server": True},
        )

    @pytest.fixture
    def messaging(self, messaging_config):
        mbus = MessagingInterface("test_tracking_embedded", messaging_config)
        yield mbus
        mbus.shutdown()

    @pytest.fixture
    def client(self):
        messages_processed = []

        def process_message(message):
            messages_processed.append(message)

        client = MessageTrackingClient("test_client", "Test Client", process_message)
        client.messages_processed = messages_processed  # Store for test access
        yield client

    @pytest.fixture
    def generator(self):
        return GemstoneGenerator(1)

    def test_track_messages_embedded_backend(self, messaging, client, generator):
        """Test message tracking with EmbeddedMessagingBackend's real-time delivery."""
        messaging.register_client(client)
        messaging.subscribe("test_topic", client)

        # Send multiple messages
        for i in range(5):
            message = Message(
                id_obj=generator.get_id(Priority.NORMAL),
                sender=AgentTag(id="sender", name="Sender"),
                topics="test_topic",
                payload={"test_data": i},
            )
            messaging.publish(client, message)

        # Wait for event-driven delivery
        time.sleep(0.5)  # EmbeddedBackend should deliver faster than InMemory

        # Verify message tracking through processed messages
        assert len(client.messages_processed) == 5

        # Test that messages were processed
        assert client.messages_processed[0].payload["test_data"] == 0

    def test_real_time_delivery_performance(self, messaging, client, generator):
        """Test that EmbeddedBackend delivers messages faster than polling backends."""
        messaging.register_client(client)
        messaging.subscribe("perf_test", client)

        start_time = time.time()

        # Send a message
        message = Message(
            id_obj=generator.get_id(Priority.URGENT),  # High priority for fastest delivery
            sender=AgentTag(id="sender", name="Sender"),
            topics="perf_test",
            payload={"timestamp": start_time},
        )
        messaging.publish(client, message)

        # Wait for delivery
        max_wait = 0.1  # 100ms should be more than enough for real-time delivery
        end_time = start_time + max_wait

        while time.time() < end_time and len(client.messages_processed) == 0:
            time.sleep(0.001)  # 1ms polling

        delivery_time = time.time() - start_time

        # EmbeddedBackend should deliver much faster than 100ms (no polling delays)
        assert len(client.messages_processed) == 1
        assert delivery_time < 0.05  # Should be under 50ms for real-time delivery
