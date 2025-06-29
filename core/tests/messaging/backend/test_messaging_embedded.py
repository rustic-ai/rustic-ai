import asyncio
import threading
import time

import pytest

from rustic_ai.core.messaging.backend.embedded_backend import (
    EmbeddedServer,
)
from rustic_ai.core.messaging.core.messaging_config import MessagingConfig

from ..core.base_test_messaging import BaseTestMessagingABC


class TestMessagingWithEmbeddedStorage(BaseTestMessagingABC):
    @pytest.fixture(scope="class")
    def server_port(self):
        """Get a fixed port for testing."""
        return 31140  # Use fixed port for messaging tests

    @pytest.fixture(scope="class")
    def shared_server(self, server_port):
        """
        Class-scoped fixture that starts a single shared server for all tests in this class.
        """
        server = EmbeddedServer(port=server_port)

        def run_server():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(server.start())
            try:
                loop.run_forever()
            finally:
                loop.run_until_complete(server.stop())
                loop.close()

        thread = threading.Thread(target=run_server, daemon=True)
        thread.start()
        time.sleep(0.2)  # Wait for server to start

        yield server, server_port

    @pytest.fixture(autouse=True)
    def cleanup_server_state(self, shared_server):
        """
        Auto-use fixture that cleans up server state before each test to prevent interference.
        """
        server, port = shared_server
        # Clean up server state before each test
        server.topics.clear()
        server.messages.clear()
        server.subscribers.clear()
        yield
        # Clean up server state after each test as well
        server.topics.clear()
        server.messages.clear()
        server.subscribers.clear()

    @pytest.fixture
    def messaging_config(self, shared_server) -> MessagingConfig:  # type: ignore
        """
        Fixture that returns an instance of the EmbeddedMessagingBackend using the shared server.
        """
        server, port = shared_server
        return MessagingConfig(
            backend_module="rustic_ai.core.messaging.backend.embedded_backend",
            backend_class="EmbeddedMessagingBackend",
            backend_config={"port": port, "auto_start_server": False},
        )

    @pytest.fixture
    def namespace(self):
        return "test_embedded_storage"

    def test_publish_and_subscribe_multiple_topics(self, messaging, message_publisher, simple_client, generator):
        """
        Test publishing a message and subscribing a client to multiple topics.
        This test is flaky due to timing sensitivities in the shared memory backend's polling mechanism.
        """
        return super().test_publish_and_subscribe_multiple_topics(
            messaging, message_publisher, simple_client, generator
        )

    def test_multiple_topics_subscription(self, message_publisher, messaging, simple_client, generator):
        """
        Test that a client subscribed to multiple topics receives messages for each topic.
        This test is flaky due to timing sensitivities in the shared memory backend's polling mechanism.
        """
        return super().test_multiple_topics_subscription(message_publisher, messaging, simple_client, generator)
