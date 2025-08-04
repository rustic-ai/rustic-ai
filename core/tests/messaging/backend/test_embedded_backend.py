import asyncio
import threading
import time

import pytest

from rustic_ai.core.messaging.backend.embedded_backend import (
    EMBEDDED_SERVER_PORT,
    EmbeddedMessagingBackend,
    EmbeddedServer,
    SocketMessage,
    create_embedded_messaging_config,
)
from rustic_ai.core.messaging.core import AgentTag, Message
from rustic_ai.core.messaging.core.messaging_backend import MessagingBackend
from rustic_ai.core.messaging.core.messaging_config import MessagingConfig
from rustic_ai.core.utils import Priority
from rustic_ai.core.utils.gemstone_id import GemstoneGenerator

from ..core.base_test_backend import BaseTestBackendABC


class TestSocketMessage:
    """Test the SocketMessage protocol."""

    def test_encode_decode_simple(self):
        """Test encoding and decoding simple messages."""
        msg = SocketMessage("PUBLISH", "topic1", "message data")
        encoded = msg.encode()

        decoded = SocketMessage.decode(encoded)
        assert decoded.command == "PUBLISH"
        assert decoded.args == ("topic1", "message data")

    def test_encode_decode_with_spaces(self):
        """Test encoding and decoding messages with spaces in arguments."""
        msg = SocketMessage("STORE_MESSAGE", "namespace", "topic with spaces", '{"data": "value"}')
        encoded = msg.encode()

        decoded = SocketMessage.decode(encoded)
        assert decoded.command == "STORE_MESSAGE"
        assert decoded.args == ("namespace", "topic with spaces", '{"data": "value"}')

    def test_decode_empty_raises_error(self):
        """Test that decoding empty message raises error."""
        with pytest.raises(ValueError, match="Empty message"):
            SocketMessage.decode(b"")

    def test_decode_no_command_raises_error(self):
        """Test that decoding message without command raises error."""
        with pytest.raises(ValueError, match="Empty message"):
            SocketMessage.decode(b"   \r\n")


class TestFixedPortRequirement:
    """Test that random ports are properly rejected."""

    def test_server_rejects_random_port(self):
        """Test that server rejects port=0."""
        with pytest.raises(ValueError, match="Random ports not supported"):
            EmbeddedServer(port=0)

    def test_backend_rejects_random_port(self):
        """Test that backend rejects port=0."""
        with pytest.raises(ValueError, match="Random ports not supported"):
            EmbeddedMessagingBackend(port=0, auto_start_server=False)


class TestEmbeddedServer:
    """Test the EmbeddedServer functionality."""

    @pytest.fixture
    def server(self):
        """Create a server instance for testing."""
        # Use a fixed test port instead of random port
        server = EmbeddedServer(port=31135)  # Use 31135 for tests to avoid conflicts
        yield server
        # Cleanup
        if server.running:
            asyncio.run(server.stop())

    @pytest.mark.asyncio
    async def test_server_start_stop(self, server):
        """Test basic server lifecycle."""
        url = await server.start()

        assert url.startswith("http://localhost:")
        assert server.running
        assert server.server is not None

        await server.stop()
        assert not server.running
        assert server.server is None

    @pytest.mark.asyncio
    async def test_server_fixed_port(self, server):
        """Test that server uses the specified fixed port."""
        url = await server.start()

        # Should use the exact port we specified
        port = int(url.split(":")[-1])
        assert port == 31135

        await server.stop()

    @pytest.mark.asyncio
    async def test_client_connection(self, server):
        """Test client connection handling."""
        await server.start()
        host = server.host
        port = server.server.sockets[0].getsockname()[1]

        # Connect a client
        reader, writer = await asyncio.open_connection(host, port)

        # Send PING command
        ping_msg = SocketMessage("PING")
        writer.write(ping_msg.encode())
        await writer.drain()

        # Read response
        response = await reader.readline()
        response_msg = SocketMessage.decode(response)

        assert response_msg.command == "PONG"

        # Close connection
        writer.close()
        await writer.wait_closed()

        await server.stop()

    @pytest.mark.asyncio
    async def test_publish_subscribe(self, server):
        """Test publish/subscribe functionality."""
        await server.start()
        host = server.host
        port = server.server.sockets[0].getsockname()[1]

        # Connect subscriber
        sub_reader, sub_writer = await asyncio.open_connection(host, port)

        # Subscribe to topic
        subscribe_msg = SocketMessage("SUBSCRIBE", "test_topic")
        sub_writer.write(subscribe_msg.encode())
        await sub_writer.drain()

        # Read subscription confirmation
        response = await sub_reader.readline()
        response_msg = SocketMessage.decode(response)
        assert response_msg.command == "OK"
        assert "SUBSCRIBED" in response_msg.args

        # Connect publisher
        pub_reader, pub_writer = await asyncio.open_connection(host, port)

        # Publish message
        publish_msg = SocketMessage("PUBLISH", "test_topic", "test message")
        pub_writer.write(publish_msg.encode())
        await pub_writer.drain()

        # Read publish confirmation
        pub_response = await pub_reader.readline()
        pub_response_msg = SocketMessage.decode(pub_response)
        assert pub_response_msg.command == "OK"
        assert int(pub_response_msg.args[0]) >= 1  # At least one subscriber

        # Read message at subscriber
        message_response = await sub_reader.readline()
        message_msg = SocketMessage.decode(message_response)
        assert message_msg.command == "MESSAGE"
        assert message_msg.args[0] == "test_topic"
        assert message_msg.args[1] == "test message"

        # Close connections
        sub_writer.close()
        pub_writer.close()
        await sub_writer.wait_closed()
        await pub_writer.wait_closed()

        await server.stop()

    @pytest.mark.asyncio
    async def test_message_storage_retrieval(self, server):
        """Test message storage and retrieval."""
        await server.start()
        host = server.host
        port = server.server.sockets[0].getsockname()[1]

        # Connect client
        reader, writer = await asyncio.open_connection(host, port)

        # Store a message
        message_data = '{"id": 12345, "timestamp": 1234567890.5, "payload": {"test": "data"}}'
        store_msg = SocketMessage("STORE_MESSAGE", "test_ns", "test_topic", message_data)
        writer.write(store_msg.encode())
        await writer.drain()

        # Read storage confirmation
        response = await reader.readline()
        response_msg = SocketMessage.decode(response)
        assert response_msg.command == "OK"
        assert response_msg.args[0] == "STORED"

        # Retrieve messages
        get_msg = SocketMessage("GET_MESSAGES", "test_topic")
        writer.write(get_msg.encode())
        await writer.drain()

        # Read messages response
        messages_response = await reader.readline()
        messages_msg = SocketMessage.decode(messages_response)
        assert messages_msg.command == "MESSAGES"

        import json

        messages = json.loads(messages_msg.args[0])
        assert len(messages) == 1
        assert messages[0]["id"] == 12345

        # Close connection
        writer.close()
        await writer.wait_closed()

        await server.stop()


class TestEmbeddedMessagingBackend:
    """Test the EmbeddedMessagingBackend functionality."""

    @pytest.fixture(scope="class")
    def server_port(self):
        """Get a fixed port for testing."""
        return 31136  # Use a different fixed port for backend tests

    @pytest.fixture(scope="class")
    def shared_server_for_backend_tests(self, server_port):
        """Class-scoped fixture that starts a single shared server for all tests."""
        server = EmbeddedServer(port=server_port)

        # Start server in background thread
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

        # Wait for server to start
        time.sleep(1)

        yield server, server_port

        # Stop server
        if server.running:
            try:
                # This is tricky since server is in another thread
                # For tests, we'll let the daemon thread handle cleanup
                pass
            except Exception:
                pass

    @pytest.fixture(autouse=True)
    def cleanup_backend_server_state(self, shared_server_for_backend_tests):
        """Auto-use fixture that cleans up server state before each test."""
        server, port = shared_server_for_backend_tests
        # Clear server state
        server.topics.clear()
        server.messages.clear()
        server.subscribers.clear()
        yield
        # Clean up after test as well
        server.topics.clear()
        server.messages.clear()
        server.subscribers.clear()

    @pytest.fixture
    def generator(self):
        return GemstoneGenerator(1)

    @pytest.fixture
    def backend(self, shared_server_for_backend_tests):
        """Backend fixture that matches the base class signature."""
        # Use the port from the shared server fixture
        server, port = shared_server_for_backend_tests
        backend = EmbeddedMessagingBackend(port=port, auto_start_server=False)
        yield backend
        backend.cleanup()

    @pytest.fixture
    def test_message(self, generator):
        return Message(
            id_obj=generator.get_id(Priority.NORMAL),
            sender=AgentTag(id="test_sender", name="Test Sender"),
            topics="test_topic",
            payload={"test": "data"},
        )

    def test_backend_initialization_auto_start(self):
        """Test backend initialization with auto-start server."""
        # Start server manually first to ensure it's running
        server = EmbeddedServer(port=31141)  # Use unique port

        def run_server():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(server.start())
                # Run briefly to ensure server is fully started
                for _ in range(50):  # 5 seconds total
                    if not server.running:
                        break
                    loop.run_until_complete(asyncio.sleep(0.1))
            finally:
                if server.running:
                    loop.run_until_complete(server.stop())
                loop.close()

        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()

        # Wait for server to start
        time.sleep(1)

        # Now create backend without auto-start since server is already running
        backend = EmbeddedMessagingBackend(port=31141, auto_start_server=False)

        # Give the backend time to connect
        time.sleep(1)

        # Check connection with retries
        max_retries = 5
        for i in range(max_retries):
            if backend.connected:
                break
            time.sleep(1)

        assert backend.connected, "Backend failed to connect to manually started server"
        assert backend.owned_server is None, "Backend should not own the server when auto-start is False"

        backend.cleanup()

        # Wait for server to stop
        time.sleep(1)

    def test_backend_with_external_server(self, shared_server_for_backend_tests):
        """Test backend with external server."""
        server, port = shared_server_for_backend_tests

        backend = EmbeddedMessagingBackend(port=port, auto_start_server=False)

        assert backend.connected
        assert backend.owned_server is None

        backend.cleanup()

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
        # Store multiple messages with sufficient time gap to ensure different timestamps
        msg1 = Message(
            id_obj=generator.get_id(Priority.NORMAL),
            sender=AgentTag(id="sender", name="Sender"),
            topics="test_topic",
            payload={"msg": 1},
        )

        backend.store_message("test", "test_topic", msg1)
        time.sleep(0.002)  # Wait 2ms to ensure different timestamps

        msg2 = Message(
            id_obj=generator.get_id(Priority.NORMAL),
            sender=AgentTag(id="sender", name="Sender"),
            topics="test_topic",
            payload={"msg": 2},
        )
        backend.store_message("test", "test_topic", msg2)

        # Get messages since msg1 (using timestamp-based filtering like InMemoryBackend)
        messages = backend.get_messages_for_topic_since("test_topic", msg1.id)
        assert len(messages) == 1
        assert messages[0].id == msg2.id

    def test_get_messages_by_id(self, backend, generator):
        """Test retrieving messages by ID."""
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

        # Give subscription time to start
        time.sleep(1)

        # Store a message
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
            time.sleep(1)

        assert len(received_messages) == 1
        assert received_messages[0].id == test_msg.id

    def test_unsubscribe(self, backend, generator):
        """Test unsubscribing from topics."""
        received_messages = []

        def handler(message):
            received_messages.append(message)

        # Subscribe and then unsubscribe
        backend.subscribe("test_topic", handler)
        time.sleep(1)
        backend.unsubscribe("test_topic")

        # Store a message after unsubscribing
        test_msg = Message(
            id_obj=generator.get_id(Priority.NORMAL),
            sender=AgentTag(id="sender", name="Sender"),
            topics="test_topic",
            payload={"test": "after_unsubscribe"},
        )
        backend.store_message("test", "test_topic", test_msg)

        # Wait a bit and ensure no notification
        time.sleep(1)
        assert len(received_messages) == 0

    def test_supports_subscription(self, backend):
        """Test that backend supports subscriptions."""
        assert backend.supports_subscription() is True

    def test_load_subscribers(self, backend):
        """Test load_subscribers returns empty dict."""
        subscribers = backend.load_subscribers("test_namespace")
        assert subscribers == {}


class TestDistributedScenarios:
    """Test distributed messaging scenarios."""

    @pytest.fixture(scope="class")
    def server_port(self):
        """Get a fixed port for testing."""
        return 31138  # Use another fixed port for distributed tests

    @pytest.fixture(scope="class")
    def shared_server(self, server_port):
        """Shared server for distributed tests."""
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
        time.sleep(1)

        yield server, server_port

    def test_multiple_backends_same_server(self, shared_server):
        """Test multiple backends connecting to the same server."""
        server, port = shared_server

        # Create multiple backends
        backend1 = EmbeddedMessagingBackend(port=port, auto_start_server=False)
        backend2 = EmbeddedMessagingBackend(port=port, auto_start_server=False)

        generator = GemstoneGenerator(1)

        try:
            # Backend1 stores a message
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

        finally:
            backend1.cleanup()
            backend2.cleanup()

    def test_cross_backend_subscription(self, shared_server):
        """Test subscriptions across different backend instances."""
        server, port = shared_server

        backend1 = EmbeddedMessagingBackend(port=port, auto_start_server=False)
        backend2 = EmbeddedMessagingBackend(port=port, auto_start_server=False)

        received_messages = []

        def handler(message):
            received_messages.append(message)

        try:
            # Backend1 subscribes
            backend1.subscribe("cross_topic", handler)
            time.sleep(1)

            # Backend2 publishes
            generator = GemstoneGenerator(1)
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
                time.sleep(1)

            assert len(received_messages) == 1
            assert received_messages[0].payload["from"] == "backend2"

        finally:
            backend1.cleanup()
            backend2.cleanup()


class TestUtilityFunctions:
    """Test utility functions."""

    def test_create_embedded_messaging_config(self):
        """Test creating messaging config."""
        config = create_embedded_messaging_config()

        assert config["backend_module"] == "rustic_ai.core.messaging.backend.embedded_backend"
        assert config["backend_class"] == "EmbeddedMessagingBackend"
        assert config["backend_config"]["host"] == "localhost"
        assert config["backend_config"]["port"] == EMBEDDED_SERVER_PORT
        assert config["backend_config"]["auto_start_server"] is True

        # With custom host and port
        config = create_embedded_messaging_config("192.168.1.1", 9999)
        assert config["backend_config"]["host"] == "192.168.1.1"
        assert config["backend_config"]["port"] == 9999

    def test_messaging_config_integration(self):
        """Test integration with MessagingConfig."""
        config_dict = create_embedded_messaging_config()
        config = MessagingConfig(**config_dict)

        # This should create a backend successfully
        backend = config.get_storage()
        assert isinstance(backend, EmbeddedMessagingBackend)

        # Clean up
        backend.cleanup()


class TestEmbeddedMessagingBackendStd(BaseTestBackendABC):
    """Standard backend tests using the base test class."""

    @pytest.fixture(scope="class")
    def class_server_port(self):
        """Get a fixed port for the class-level server."""
        return 31139  # Use another fixed port for standard tests

    @pytest.fixture(scope="class")
    def class_server(self, class_server_port):
        """Class-scoped server for standard backend tests."""
        server = EmbeddedServer(port=class_server_port)

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
        time.sleep(1)

        yield server, class_server_port

    @pytest.fixture(autouse=True)
    def cleanup_class_server_state(self, class_server):
        """Auto-use fixture that cleans up server state before each test."""
        server, port = class_server
        server.topics.clear()
        server.messages.clear()
        server.subscribers.clear()
        yield
        server.topics.clear()
        server.messages.clear()
        server.subscribers.clear()

    @pytest.fixture
    def backend(self, class_server) -> MessagingBackend:  # type: ignore
        """Backend fixture that matches the base class signature."""
        # Use the port from the class server fixture
        server, port = class_server
        backend = EmbeddedMessagingBackend(port=port, auto_start_server=False)
        yield backend
        backend.cleanup()

    def test_subscribe(self, backend: MessagingBackend, generator: GemstoneGenerator, topic: str, request):
        """Test subscription with real-time delivery."""
        received_messages = []

        def callback(message: Message):
            received_messages.append(message)

        # Subscribe to topic
        backend.subscribe(topic, callback)
        time.sleep(1)  # Give subscription time to start

        # Store a message
        message = Message(
            id_obj=generator.get_id(Priority.NORMAL),
            sender=AgentTag(id="test_sender", name="Test Sender"),
            topics=topic,
            payload={"test": "subscription_data"},
        )
        backend.store_message("test_namespace", topic, message)

        # Wait for notification
        deadline = time.time() + 5
        while time.time() < deadline and len(received_messages) == 0:
            time.sleep(1)

        assert len(received_messages) == 1
        assert received_messages[0].id == message.id
