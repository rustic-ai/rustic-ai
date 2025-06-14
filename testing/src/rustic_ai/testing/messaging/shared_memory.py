import time
from typing import Any, Dict, Generator, List, Optional, Tuple

import pytest

from rustic_ai.core.messaging.backend.shared_memory_backend import (
    SharedMemoryMessagingBackend,
    SharedMemoryServer,
    create_shared_messaging_config,
    start_shared_memory_server,
)
from rustic_ai.core.messaging.core.messaging_config import MessagingConfig


@pytest.fixture
def shared_memory_server() -> Generator[tuple[SharedMemoryServer, str], None, None]:
    """Pytest fixture that provides a shared memory server for testing."""
    server, url = start_shared_memory_server()
    try:
        yield server, url
    finally:
        server.cleanup()
        server.stop()


@pytest.fixture
def shared_messaging_config(shared_memory_server) -> MessagingConfig:
    """Pytest fixture that provides a MessagingConfig for shared memory backend."""
    server, url = shared_memory_server
    config_dict = create_shared_messaging_config(url)
    return MessagingConfig(**config_dict)


@pytest.fixture
def shared_messaging_backend(shared_memory_server) -> Generator[SharedMemoryMessagingBackend, None, None]:
    """Pytest fixture that provides a SharedMemoryMessagingBackend for testing."""
    server, url = shared_memory_server
    backend = SharedMemoryMessagingBackend(server_url=url, auto_start_server=False)
    try:
        yield backend
    finally:
        backend.cleanup()


class SharedMemoryTestHelper:
    """Helper class for testing with shared memory messaging."""

    def __init__(self, server_url: Optional[str] = None):
        if server_url:
            self.server = None
            self.server_url = server_url
        else:
            self.server, self.server_url = start_shared_memory_server()

    def get_messaging_config(self) -> MessagingConfig:
        """Get a MessagingConfig for this shared memory server."""
        config_dict = create_shared_messaging_config(self.server_url)
        return MessagingConfig(**config_dict)

    def get_backend(self) -> SharedMemoryMessagingBackend:
        """Get a SharedMemoryMessagingBackend for this server."""
        return SharedMemoryMessagingBackend(server_url=self.server_url, auto_start_server=False)

    def wait_for_messages(
        self, backend: SharedMemoryMessagingBackend, topic: str, expected_count: int, timeout: float = 5.0
    ) -> bool:
        """
        Wait for a specific number of messages to appear in a topic.

        Args:
            backend: The messaging backend to check
            topic: The topic to monitor
            expected_count: Number of messages to wait for
            timeout: Maximum time to wait in seconds

        Returns:
            True if expected_count messages were found, False if timeout
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            messages = backend.get_messages_for_topic(topic)
            if len(messages) >= expected_count:
                return True
            time.sleep(0.1)
        return False

    def cleanup(self):
        """Clean up the server if we own it."""
        if self.server:
            self.server.cleanup()
            self.server.stop()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()


class DistributedTestScenario:
    """Helper for testing distributed messaging scenarios."""

    def __init__(self, server_url: Optional[str] = None):
        self.helper = SharedMemoryTestHelper(server_url)
        self.backends: List[Tuple[str, SharedMemoryMessagingBackend]] = []
        self.received_messages: Dict[str, List[Any]] = {}

    def create_backend(self, backend_id: str) -> SharedMemoryMessagingBackend:
        """Create a new backend instance for testing."""
        backend = self.helper.get_backend()
        self.backends.append((backend_id, backend))
        self.received_messages[backend_id] = []
        return backend

    def setup_subscriber(self, backend_id: str, topic: str) -> None:
        """Set up a subscriber that collects messages."""
        backend = self.get_backend(backend_id)

        def handler(message):
            self.received_messages[backend_id].append(message)

        backend.subscribe(topic, handler)

    def get_backend(self, backend_id: str) -> SharedMemoryMessagingBackend:
        """Get a backend by ID."""
        for bid, backend in self.backends:
            if bid == backend_id:
                return backend
        raise ValueError(f"Backend {backend_id} not found")

    def get_received_messages(self, backend_id: str) -> list:
        """Get messages received by a specific backend."""
        return self.received_messages.get(backend_id, [])

    def wait_for_message_delivery(self, backend_id: str, expected_count: int, timeout: float = 5.0) -> bool:
        """Wait for messages to be delivered to a specific backend."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if len(self.received_messages.get(backend_id, [])) >= expected_count:
                return True
            time.sleep(0.1)
        return False

    def cleanup(self):
        """Clean up all backends and the helper."""
        for _, backend in self.backends:
            backend.cleanup()
        self.helper.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()


def create_test_message_dict(
    message_id: int, sender_id: str = "test_sender", topic: str = "test_topic", payload: Optional[dict] = None
) -> dict:
    """Create a test message dictionary for testing."""
    if payload is None:
        payload = {"test": "data"}

    return {
        "id": message_id,
        "sender": {"id": sender_id, "name": sender_id},
        "topics": topic,
        "payload": payload,
        "format": "generic_json",
        "timestamp": time.time(),
        "priority": 4,
        "thread": [message_id],
        "recipient_list": [],
        "in_response_to": None,
        "conversation_id": None,
        "forward_header": None,
        "routing_slip": None,
        "message_history": [],
        "ttl": None,
        "is_error_message": False,
        "traceparent": None,
        "session_state": None,
        "topic_published_to": None,
        "enrich_with_history": 0,
    }
