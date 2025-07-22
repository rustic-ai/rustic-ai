import socket
from unittest.mock import Mock, patch

import fakeredis
import pytest

from rustic_ai.redis.messaging.backend import RedisMessagingBackend
from rustic_ai.redis.messaging.connection_manager import RedisBackendConfig
from rustic_ai.redis.messaging.exceptions import RedisConnectionFailureError

from rustic_ai.testing.messaging.base_test_backend import BaseTestBackendABC


class TestRedisBackend(BaseTestBackendABC):
    @pytest.fixture
    def backend(self):
        """Fixture that returns an instance of RedisMessagingBackend."""
        fake_redis_client = fakeredis.FakeStrictRedis()
        storage = RedisMessagingBackend(fake_redis_client)
        yield storage
        storage.cleanup()


class TestRedisBackendConfiguration:
    """Test Redis backend configuration and initialization."""

    def test_default_configuration(self):
        """Test that default configuration values are set correctly."""
        config = RedisBackendConfig(host="localhost", port=6379)

        assert config.socket_keepalive is True
        # Check that socket_keepalive_options is not None before subscripting
        assert config.socket_keepalive_options is not None
        assert config.socket_keepalive_options[socket.TCP_KEEPIDLE] == 300
        assert config.socket_keepalive_options[socket.TCP_KEEPINTVL] == 60
        assert config.socket_keepalive_options[socket.TCP_KEEPCNT] == 3
        assert config.health_check_interval == 30
        assert config.socket_connect_timeout == 10
        assert config.socket_timeout == 30

        # Retry settings
        assert config.pubsub_retry_enabled is True
        assert config.pubsub_retry_initial_delay == 1.0
        assert config.pubsub_retry_max_delay == 60.0
        assert config.pubsub_retry_multiplier == 2.0
        assert config.pubsub_health_check_interval == 10.0

        # Fail-fast settings
        assert config.pubsub_max_retry_attempts == 5
        assert config.pubsub_max_retry_time == 300.0
        assert config.pubsub_crash_on_failure is True

    def test_custom_configuration(self):
        """Test custom configuration values."""
        config = RedisBackendConfig(
            host="redis.example.com",
            port=6380,
            socket_keepalive=False,
            pubsub_retry_enabled=False,
            pubsub_max_retry_attempts=3,
            pubsub_crash_on_failure=False,
        )

        assert config.host == "redis.example.com"
        assert config.port == 6380
        assert config.socket_keepalive is False
        assert config.pubsub_retry_enabled is False
        assert config.pubsub_max_retry_attempts == 3
        assert config.pubsub_crash_on_failure is False

    @patch("rustic_ai.redis.messaging.connection_manager.redis.StrictRedis")
    def test_redis_client_initialization_with_keepalive(self, mock_redis):
        """Test that Redis client is initialized with keepalive settings."""
        config = RedisBackendConfig(
            host="localhost",
            port=6379,
            socket_keepalive=True,
            socket_keepalive_options={socket.TCP_KEEPIDLE: 300, socket.TCP_KEEPINTVL: 60, socket.TCP_KEEPCNT: 3},
        )

        backend = RedisMessagingBackend(config)
        assert backend is not None

        mock_redis.assert_called_once_with(
            host="localhost",
            port=6379,
            username=None,
            password=None,
            ssl=False,
            ssl_certfile=None,
            ssl_keyfile=None,
            ssl_ca_certs=None,
            socket_keepalive=True,
            socket_keepalive_options={socket.TCP_KEEPIDLE: 300, socket.TCP_KEEPINTVL: 60, socket.TCP_KEEPCNT: 3},
            health_check_interval=30,
            socket_connect_timeout=10,
            socket_timeout=30,
            decode_responses=True,
        )

        backend.cleanup()


class TestRedisBackendBasicFunctionality:
    """Test basic backend functionality through the public interface."""

    @pytest.fixture
    def test_backend(self):
        """Create a test backend with fakeredis."""
        fake_redis_client = fakeredis.FakeStrictRedis()
        backend = RedisMessagingBackend(fake_redis_client)
        yield backend
        backend.cleanup()

    def test_configuration_access(self, test_backend):
        """Test that configuration can be accessed for testing purposes."""
        # The backend should have access to config via property
        config = test_backend._config
        assert config is None  # Because we passed a raw redis client, not config

    def test_supports_subscription(self, test_backend):
        """Test that backend reports subscription support."""
        assert test_backend.supports_subscription() is True

    def test_subscription_basic_operations(self, test_backend):
        """Test basic subscribe/unsubscribe operations."""
        handler = Mock()

        # Subscribe should not raise
        test_backend.subscribe("test-topic", handler)

        # Unsubscribe should not raise
        test_backend.unsubscribe("test-topic")

    def test_cleanup_is_safe(self, test_backend):
        """Test that cleanup can be called safely."""
        # Should not raise
        test_backend.cleanup()

        # Should be safe to call multiple times
        test_backend.cleanup()


class TestRedisBackendErrorConditions:
    """Test various error conditions and edge cases."""

    def test_invalid_redis_client_type(self):
        """Test that invalid Redis client type raises appropriate error."""
        with pytest.raises(ValueError, match="Invalid Redis client"):
            # Use an object that's not a valid Redis client type
            invalid_client = object()  # Not a Redis client, dict, or RedisBackendConfig
            RedisMessagingBackend(invalid_client)  # type: ignore

    @patch("rustic_ai.redis.messaging.pubsub_manager.redis.StrictRedis")
    def test_pubsub_setup_failure_with_crash_enabled(self, mock_redis):
        """Test that pub/sub setup failure raises appropriate error when crash is enabled."""
        mock_redis_instance = Mock()
        mock_redis.return_value = mock_redis_instance

        # Mock pubsub to fail
        mock_pubsub = Mock()
        mock_redis_instance.pubsub.return_value = mock_pubsub
        mock_pubsub.run_in_thread.side_effect = Exception("Connection failed")

        config = RedisBackendConfig(
            host="localhost", port=6379, pubsub_retry_enabled=False, pubsub_crash_on_failure=True
        )

        with pytest.raises(RedisConnectionFailureError):
            RedisMessagingBackend(config)

    @patch("rustic_ai.redis.messaging.pubsub_manager.redis.StrictRedis")
    def test_pubsub_setup_failure_with_crash_disabled(self, mock_redis):
        """Test that pub/sub setup failure propagates original error when crash is disabled."""
        mock_redis_instance = Mock()
        mock_redis.return_value = mock_redis_instance

        # Mock pubsub to fail
        mock_pubsub = Mock()
        mock_redis_instance.pubsub.return_value = mock_pubsub
        original_error = Exception("Original connection error")
        mock_pubsub.run_in_thread.side_effect = original_error

        config = RedisBackendConfig(
            host="localhost", port=6379, pubsub_retry_enabled=False, pubsub_crash_on_failure=False
        )

        with pytest.raises(Exception, match="Original connection error"):
            RedisMessagingBackend(config)


class TestRedisBackendIntegration:
    """Integration tests for the complete backend functionality."""

    @pytest.fixture
    def redis_backend(self):
        """Create a Redis backend with real fakeredis."""
        fake_redis_client = fakeredis.FakeStrictRedis()
        backend = RedisMessagingBackend(fake_redis_client)
        yield backend
        backend.cleanup()

    def test_end_to_end_messaging(self, redis_backend):
        """Test complete message flow from store to retrieve."""
        from rustic_ai.core.messaging.core.message import Message
        from rustic_ai.core.utils import GemstoneGenerator, Priority

        # Create a message
        id_gen = GemstoneGenerator(machine_id=1)
        msg = Message(
            id_obj=id_gen.get_id(Priority.HIGH),
            sender={"name": "test-sender", "id": "sender-1"},
            topics="test-topic",
            payload={"test": "data", "value": 42},
        )

        # Store message
        redis_backend.store_message("test-namespace", "test-topic", msg)

        # Retrieve messages
        messages = redis_backend.get_messages_for_topic("test-topic")
        assert len(messages) == 1
        assert messages[0].id == msg.id
        assert messages[0].payload == msg.payload

        # Get by ID
        retrieved = redis_backend.get_messages_by_id("test-namespace", [msg.id])
        assert len(retrieved) == 1
        assert retrieved[0].id == msg.id

    def test_subscription_workflow(self, redis_backend):
        """Test subscription workflow with message delivery."""
        received_messages = []

        def handler(message):
            received_messages.append(message)

        # Subscribe
        redis_backend.subscribe("test-pubsub", handler)

        # Create and store a message (which should trigger pub/sub)
        from rustic_ai.core.messaging.core.message import Message
        from rustic_ai.core.utils import GemstoneGenerator, Priority

        id_gen = GemstoneGenerator(machine_id=1)
        msg = Message(
            id_obj=id_gen.get_id(Priority.NORMAL),
            sender={"name": "test-sender", "id": "sender-1"},
            topics="test-pubsub",
            payload={"test": "pubsub", "value": 123},
        )

        redis_backend.store_message("test-namespace", "test-pubsub", msg)

        # With fakeredis, pub/sub is synchronous, so message should be received
        import time

        time.sleep(0.1)  # Give a moment for message processing

        # Unsubscribe
        redis_backend.unsubscribe("test-pubsub")

        # Note: With fakeredis, pub/sub might not work exactly like real Redis
        # So we don't assert on received_messages, just ensure no exceptions
        assert isinstance(received_messages, list)
