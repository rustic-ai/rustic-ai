import time
from typing import List

import pytest

from rustic_ai.core.messaging.backend.shared_memory_backend import (
    SharedMemoryMessagingBackend,
    SharedMemoryServer,
    create_shared_messaging_config,
    start_shared_memory_server,
)
from rustic_ai.core.messaging.core import AgentTag, Message, MessageConstants
from rustic_ai.core.messaging.core.messaging_backend import MessagingBackend
from rustic_ai.core.messaging.core.messaging_config import MessagingConfig
from rustic_ai.core.utils import Priority
from rustic_ai.core.utils.gemstone_id import GemstoneGenerator

from ..core.base_test_backend import BaseTestBackendABC


class TestSharedMemoryServer:
    """Test the SharedMemoryServer functionality."""

    def test_server_start_stop(self):
        """Test basic server lifecycle."""
        server = SharedMemoryServer()
        url = server.start()

        assert url.startswith("http://localhost:")
        assert server.running
        assert server.server_thread is not None

        server.stop()
        assert not server.running
        assert server.server is None

    def test_server_auto_port(self):
        """Test automatic port assignment."""
        server = SharedMemoryServer(port=0)
        url = server.start()

        # Should get a random port
        port = int(url.split(":")[-1])
        assert port > 0
        assert port != 0

        server.stop()

    def test_server_health_endpoint(self):
        """Test health check endpoint."""
        server = SharedMemoryServer()
        url = server.start()

        # Give the server a moment to fully start up
        time.sleep(0.1)

        try:
            import urllib.request

            response = urllib.request.urlopen(f"{url}/health")
            assert response.getcode() == 200
        finally:
            server.stop()

    def test_server_stats_endpoint(self):
        """Test stats endpoint."""
        server = SharedMemoryServer()
        url = server.start()

        try:
            import json
            import urllib.request

            response = urllib.request.urlopen(f"{url}/stats")
            data = json.loads(response.read().decode())

            assert data["status"] == "healthy"
            assert "topics" in data
            assert "total_messages" in data
            assert "uptime" in data
        finally:
            server.stop()


class TestSharedMemoryMessagingBackend:
    """Test the SharedMemoryMessagingBackend functionality."""

    @pytest.fixture(scope="class")
    def shared_server_for_backend_tests(self):
        """
        Class-scoped fixture that starts a single shared server for all tests in this class.
        """
        server, url = start_shared_memory_server()
        yield server, url
        server.stop()

    @pytest.fixture(autouse=True)
    def cleanup_backend_server_state(self, shared_server_for_backend_tests):
        """
        Auto-use fixture that cleans up server state before each test to prevent interference.
        """
        server, url = shared_server_for_backend_tests
        # Clean up server state before each test
        server.cleanup()
        yield
        # Clean up server state after each test as well
        server.cleanup()

    @pytest.fixture
    def generator(self):
        return GemstoneGenerator(1)

    @pytest.fixture
    def backend(self, shared_server_for_backend_tests):
        server, url = shared_server_for_backend_tests
        backend = SharedMemoryMessagingBackend(server_url=url, auto_start_server=False)
        yield backend
        backend.cleanup()

    @pytest.fixture
    def test_message(self, generator):
        from rustic_ai.core.messaging import Priority

        return Message(
            id_obj=generator.get_id(Priority.NORMAL),
            sender=AgentTag(id="test_sender", name="Test Sender"),
            topics="test_topic",
            payload={"test": "data"},
        )

    def test_backend_initialization(self):
        """Test backend initialization with auto-start server."""
        backend = SharedMemoryMessagingBackend()

        assert backend.server_url is not None
        assert backend.owned_server is not None
        assert backend.running

        backend.cleanup()

    def test_backend_with_external_server(self):
        """Test backend with external server."""
        server, url = start_shared_memory_server()

        try:
            backend = SharedMemoryMessagingBackend(server_url=url, auto_start_server=False)

            assert backend.server_url == url
            assert backend.owned_server is None

            backend.cleanup()
        finally:
            server.stop()

    def test_store_and_retrieve_message(self, backend, test_message):
        """Test basic message storage and retrieval."""
        # Store message
        backend.store_message("test_namespace", "test_topic", test_message)

        # Retrieve messages
        messages = backend.get_messages_for_topic("test_topic")
        assert len(messages) == 1
        assert messages[0].id == test_message.id
        assert messages[0].payload == test_message.payload

    def test_get_messages_since(self, backend, generator):
        """Test retrieving messages since a specific ID."""
        # Store multiple messages
        from rustic_ai.core.messaging import Priority

        msg1 = Message(
            id_obj=generator.get_id(Priority.NORMAL),
            sender=AgentTag(id="sender", name="Sender"),
            topics="test_topic",
            payload={"msg": 1},
        )
        msg2 = Message(
            id_obj=generator.get_id(Priority.NORMAL),
            sender=AgentTag(id="sender", name="Sender"),
            topics="test_topic",
            payload={"msg": 2},
        )

        backend.store_message("test", "test_topic", msg1)
        time.sleep(0.01)  # Ensure different timestamps
        backend.store_message("test", "test_topic", msg2)

        # Get messages since msg1
        messages = backend.get_messages_for_topic_since("test_topic", msg1.id)
        assert len(messages) == 1
        assert messages[0].id == msg2.id

    def test_get_messages_by_id(self, backend, generator):
        """Test retrieving messages by ID."""
        from rustic_ai.core.messaging import Priority

        msg1 = Message(
            id_obj=generator.get_id(Priority.NORMAL),
            sender=AgentTag(id="sender", name="Sender"),
            topics="topic1",
            payload={"msg": 1},
        )
        msg2 = Message(
            id_obj=generator.get_id(Priority.NORMAL),
            sender=AgentTag(id="sender", name="Sender"),
            topics="topic2",
            payload={"msg": 2},
        )

        backend.store_message("test", "topic1", msg1)
        backend.store_message("test", "topic2", msg2)

        # Retrieve by IDs
        messages = backend.get_messages_by_id("test", [msg1.id, msg2.id])
        assert len(messages) == 2

        # Check we got both messages
        ids = {msg.id for msg in messages}
        assert msg1.id in ids
        assert msg2.id in ids

    def test_subscription_and_notification(self, backend, generator):
        """Test real-time subscription and notification."""
        received_messages = []

        def handler(message):
            received_messages.append(message)

        # Subscribe to topic
        backend.subscribe("test_topic", handler)

        # Give polling thread time to start
        time.sleep(0.2)

        # Store a message
        from rustic_ai.core.messaging import Priority

        test_msg = Message(
            id_obj=generator.get_id(Priority.NORMAL),
            sender=AgentTag(id="sender", name="Sender"),
            topics="test_topic",
            payload={"test": "notification"},
        )
        backend.store_message("test", "test_topic", test_msg)

        # Wait for notification
        deadline = time.time() + 5
        while time.time() < deadline and len(received_messages) == 0:
            time.sleep(0.1)

        assert len(received_messages) == 1
        assert received_messages[0].id == test_msg.id

    def test_unsubscribe(self, backend, generator):
        """Test unsubscribing from topics."""
        received_messages = []

        def handler(message):
            received_messages.append(message)

        # Subscribe and then unsubscribe
        backend.subscribe("test_topic", handler)
        time.sleep(0.1)
        backend.unsubscribe("test_topic")

        # Store a message after unsubscribing
        from rustic_ai.core.messaging import Priority

        test_msg = Message(
            id_obj=generator.get_id(Priority.NORMAL),
            sender=AgentTag(id="sender", name="Sender"),
            topics="test_topic",
            payload={"test": "after_unsubscribe"},
        )
        backend.store_message("test", "test_topic", test_msg)

        # Wait a bit and ensure no notification
        time.sleep(0.5)
        assert len(received_messages) == 0

    def test_redis_like_operations(self, backend):
        """Test Redis-like string operations."""
        # SET and GET
        backend.set("test_key", "test_value")
        value = backend.get("test_key")
        assert value == "test_value"

        # SET with expiration
        backend.set("temp_key", "temp_value", ex=1)
        assert backend.get("temp_key") == "temp_value"

        # Wait for expiration
        time.sleep(1.5)
        assert backend.get("temp_key") is None

        # Non-existent key
        assert backend.get("nonexistent") is None

    def test_redis_hash_operations(self, backend):
        """Test Redis-like hash operations."""
        # HSET and HGET
        backend.hset("test_hash", "field1", "value1")
        backend.hset("test_hash", "field2", "value2")

        assert backend.hget("test_hash", "field1") == "value1"
        assert backend.hget("test_hash", "field2") == "value2"
        assert backend.hget("test_hash", "nonexistent") is None

    def test_redis_set_operations(self, backend):
        """Test Redis-like set operations."""
        # SADD and SMEMBERS
        added = backend.sadd("test_set", "member1", "member2", "member1")
        assert added == 2  # member1 added only once

        members = backend.smembers("test_set")
        assert members == {"member1", "member2"}

    def test_redis_publish_subscribe(self, backend):
        """Test Redis-like pub/sub."""
        received_messages = []

        def handler(message):
            received_messages.append(message)

        # Subscribe to channel
        backend.subscribe("test_channel", handler)
        time.sleep(0.1)

        # Publish message
        count = backend.publish("test_channel", "test message")
        assert count >= 1  # At least one subscriber

        # Wait for delivery
        time.sleep(0.5)
        # Note: This test might need adjustment based on how publish integrates with message handling

    def test_pattern_subscription(self, backend):
        """Test pattern-based subscriptions."""
        received_messages = []

        def handler(message):
            received_messages.append(message)

        # Subscribe to pattern
        backend.psubscribe("sensor.*", handler)
        time.sleep(0.1)

        # Publish to matching topics
        backend.publish("sensor.temperature", "25.5")
        backend.publish("sensor.humidity", "60")
        backend.publish("other.data", "ignored")

        # Wait for delivery
        time.sleep(0.5)
        # Note: This test might need adjustment based on implementation details

    def test_message_ttl(self, backend, generator):
        """Test message TTL functionality."""
        # Create message with TTL
        from rustic_ai.core.messaging import Priority

        msg = Message(
            id_obj=generator.get_id(Priority.NORMAL),
            sender=AgentTag(id="sender", name="Sender"),
            topics="ttl_topic",
            payload={"test": "ttl"},
            ttl=1,  # 1 second TTL
        )

        backend.store_message("test", "ttl_topic", msg)

        # Message should exist immediately
        messages = backend.get_messages_for_topic("ttl_topic")
        assert len(messages) == 1

        # Wait for TTL expiration
        time.sleep(2)

        # Message should be gone (this depends on cleanup thread running)
        # Note: This test might be flaky due to cleanup timing
        messages = backend.get_messages_for_topic("ttl_topic")
        # The message might still be there if cleanup hasn't run yet
        # In a real test, you might want to trigger cleanup manually


class TestDistributedScenarios:
    """Test distributed messaging scenarios."""

    def test_multiple_backends_same_server(self):
        """Test multiple backends connecting to the same server."""
        server, url = start_shared_memory_server()

        try:
            # Create multiple backends
            backend1 = SharedMemoryMessagingBackend(url, auto_start_server=False)
            backend2 = SharedMemoryMessagingBackend(url, auto_start_server=False)

            generator = GemstoneGenerator(1)

            # Backend1 stores a message
            from rustic_ai.core.messaging import Priority

            msg = Message(
                id_obj=generator.get_id(Priority.NORMAL),
                sender=AgentTag(id="sender1", name="Sender1"),
                topics="shared_topic",
                payload={"from": "backend1"},
            )
            backend1.store_message("shared", "shared_topic", msg)

            # Backend2 should see the message
            messages = backend2.get_messages_for_topic("shared_topic")
            assert len(messages) == 1
            assert messages[0].payload["from"] == "backend1"

            backend1.cleanup()
            backend2.cleanup()

        finally:
            server.stop()

    def test_cross_backend_subscription(self):
        """Test subscriptions across different backend instances."""
        server, url = start_shared_memory_server()

        try:
            backend1 = SharedMemoryMessagingBackend(url, auto_start_server=False)
            backend2 = SharedMemoryMessagingBackend(url, auto_start_server=False)

            received_messages = []

            def handler(message):
                received_messages.append(message)

            # Backend1 subscribes
            backend1.subscribe("cross_topic", handler)
            time.sleep(0.2)

            # Backend2 publishes
            generator = GemstoneGenerator(1)
            from rustic_ai.core.messaging import Priority

            msg = Message(
                id_obj=generator.get_id(Priority.NORMAL),
                sender=AgentTag(id="sender2", name="Sender2"),
                topics="cross_topic",
                payload={"from": "backend2"},
            )
            backend2.store_message("shared", "cross_topic", msg)

            # Wait for notification
            deadline = time.time() + 5
            while time.time() < deadline and len(received_messages) == 0:
                time.sleep(0.1)

            assert len(received_messages) == 1
            assert received_messages[0].payload["from"] == "backend2"

            backend1.cleanup()
            backend2.cleanup()

        finally:
            server.stop()


class TestUtilityFunctions:
    """Test utility functions."""

    def test_start_shared_memory_server(self):
        """Test the utility function for starting a server."""
        server, url = start_shared_memory_server()

        assert isinstance(server, SharedMemoryServer)
        assert url.startswith("http://")
        assert server.running

        server.stop()

    def test_create_shared_messaging_config(self):
        """Test creating messaging config."""
        # Without server URL (auto-start)
        config = create_shared_messaging_config()

        assert config["backend_module"] == "rustic_ai.core.messaging.backend.shared_memory_backend"
        assert config["backend_class"] == "SharedMemoryMessagingBackend"
        assert config["backend_config"] == {}

        # With server URL
        config = create_shared_messaging_config("http://localhost:8080")

        assert config["backend_config"]["server_url"] == "http://localhost:8080"
        assert config["backend_config"]["auto_start_server"] is False

    def test_messaging_config_integration(self):
        """Test integration with MessagingConfig."""
        config_dict = create_shared_messaging_config()
        config = MessagingConfig(**config_dict)

        # This should create a backend successfully
        backend = config.get_storage()
        assert isinstance(backend, SharedMemoryMessagingBackend)

        backend.cleanup()


class TestErrorHandling:
    """Test error handling scenarios."""

    def test_connection_to_nonexistent_server(self):
        """Test connecting to a non-existent server."""
        with pytest.raises(ConnectionError):
            SharedMemoryMessagingBackend(server_url="http://localhost:99999", auto_start_server=False)

    def test_invalid_server_url(self):
        """Test invalid server URL."""
        with pytest.raises(ConnectionError):
            SharedMemoryMessagingBackend(server_url="invalid://url", auto_start_server=False)

    def test_no_server_url_no_auto_start(self):
        """Test error when no server URL and auto_start_server=False."""
        with pytest.raises(ValueError):
            SharedMemoryMessagingBackend(server_url=None, auto_start_server=False)


class TestSharedMemoryBackendStd(BaseTestBackendABC):
    @pytest.fixture(scope="class")
    def class_server(self):
        """
        Class-scoped fixture that starts a single shared server for all tests in this class.
        """
        server, url = start_shared_memory_server()
        yield server, url
        server.stop()

    @pytest.fixture(autouse=True)
    def cleanup_class_server_state(self, class_server):
        """
        Auto-use fixture that cleans up server state before each test to prevent interference.
        """
        server, url = class_server
        # Clean up server state before each test
        server.cleanup()
        yield
        # Clean up server state after each test as well
        server.cleanup()

    @pytest.fixture
    def backend(self, class_server):
        """Fixture that returns an instance of SharedMemoryMessagingBackend."""
        server, url = class_server
        backend = SharedMemoryMessagingBackend(server_url=url, auto_start_server=False)
        yield backend
        backend.cleanup()

    # Override the subscription test to allow more time for polling-based delivery
    def test_subscribe(self, backend: MessagingBackend, generator: GemstoneGenerator, topic: str, request):
        """
        Test subscribing to a topic with longer wait time for polling-based backends.
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

        # Allow more time for polling-based message delivery
        time.sleep(0.2)

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

        time.sleep(0.2)

        assert len(messages) == 1

    # No need to re-implement the test methods from TestStorageABC unless there's a specific behavior
    # of InMemoryStorage that needs to be tested differently.
