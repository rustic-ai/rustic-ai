import pytest

from rustic_ai.core.messaging.backend.shared_memory_backend import (
    start_shared_memory_server,
)
from rustic_ai.core.messaging.core.messaging_config import MessagingConfig

from ..core.base_test_messaging import BaseTestMessagingABC


class TestMessagingWithInMemoryStorage(BaseTestMessagingABC):
    @pytest.fixture(scope="class")
    def shared_server(self):
        """
        Class-scoped fixture that starts a single shared server for all tests in this class.
        """
        server, url = start_shared_memory_server()
        yield server, url
        server.stop()

    @pytest.fixture(autouse=True)
    def cleanup_server_state(self, shared_server):
        """
        Auto-use fixture that cleans up server state before each test to prevent interference.
        """
        server, url = shared_server
        # Clean up server state before each test
        server.cleanup()
        yield
        # Clean up server state after each test as well
        server.cleanup()

    @pytest.fixture
    def messaging_config(self, shared_server) -> MessagingConfig:  # type: ignore
        """
        Fixture that returns an instance of the SharedMemoryMessagingBackend using the shared server.
        """
        server, url = shared_server
        return MessagingConfig(
            backend_module="rustic_ai.core.messaging.backend.shared_memory_backend",
            backend_class="SharedMemoryMessagingBackend",
            backend_config={"server_url": url, "auto_start_server": False},
        )

    @pytest.fixture
    def namespace(self):
        return "test_shared_memory"

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
