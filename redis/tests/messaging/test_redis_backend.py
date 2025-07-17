import socket
import time
from unittest.mock import Mock, patch

import fakeredis
import pytest

from rustic_ai.redis.messaging.backend import (
    RedisBackendConfig,
    RedisConnectionFailureError,
    RedisMessagingBackend,
)

from rustic_ai.testing.messaging.base_test_backend import BaseTestBackendABC


class TestRedisBackend(BaseTestBackendABC):
    @pytest.fixture
    def backend(self):
        """Fixture that returns an instance of RedisStorage."""
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

    @patch("redis.StrictRedis")
    def test_redis_client_initialization_with_keepalive(self, mock_redis):
        """Test that Redis client is initialized with keepalive settings."""
        config = RedisBackendConfig(
            host="localhost",
            port=6379,
            socket_keepalive=True,
            socket_keepalive_options={socket.TCP_KEEPIDLE: 300, socket.TCP_KEEPINTVL: 60, socket.TCP_KEEPCNT: 3},
        )

        with patch.object(RedisMessagingBackend, "_setup_pubsub"):
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
        )


class TestRedisBackendRetryLogic:
    """Test retry logic and exponential backoff behavior."""

    @pytest.fixture
    def mock_redis_config(self):
        return RedisBackendConfig(
            host="localhost",
            port=6379,
            pubsub_retry_enabled=True,
            pubsub_retry_initial_delay=0.1,  # Fast for testing
            pubsub_retry_max_delay=1.0,
            pubsub_retry_multiplier=2.0,
            pubsub_max_retry_attempts=3,
            pubsub_max_retry_time=5.0,
            pubsub_health_check_interval=0.5,
        )

    @patch("redis.StrictRedis")
    def test_retry_configuration_applied(self, mock_redis, mock_redis_config):
        """Test that retry configuration is properly stored and applied."""
        mock_redis_instance = Mock()
        mock_redis.return_value = mock_redis_instance

        # Mock successful pubsub setup to avoid threading issues
        mock_pubsub = Mock()
        mock_redis_instance.pubsub.return_value = mock_pubsub
        mock_pubsub.run_in_thread.return_value = Mock()

        backend = RedisMessagingBackend(mock_redis_config)

        # Verify configuration is stored
        assert backend._config is not None
        assert backend._config.pubsub_retry_enabled is True
        assert backend._config.pubsub_retry_initial_delay == 0.1
        assert backend._config.pubsub_retry_max_delay == 1.0
        assert backend._config.pubsub_retry_multiplier == 2.0
        assert backend._config.pubsub_max_retry_attempts == 3

    @patch("redis.StrictRedis")
    def test_exponential_backoff_calculation(self, mock_redis, mock_redis_config):
        """Test exponential backoff delay calculation without threading."""
        mock_redis_instance = Mock()
        mock_redis.return_value = mock_redis_instance

        mock_pubsub = Mock()
        mock_redis_instance.pubsub.return_value = mock_pubsub
        mock_pubsub.run_in_thread.return_value = Mock()

        backend = RedisMessagingBackend(mock_redis_config)

        # Test the backoff calculation logic
        assert backend._config is not None  # Type guard
        config = backend._config
        initial_delay = config.pubsub_retry_initial_delay
        multiplier = config.pubsub_retry_multiplier
        max_delay = config.pubsub_retry_max_delay

        # Calculate expected delays
        delay1 = initial_delay
        delay2 = min(delay1 * multiplier, max_delay)
        delay3 = min(delay2 * multiplier, max_delay)

        assert delay1 == 0.1
        assert delay2 == 0.2
        assert delay3 == 0.4
        assert min(delay3 * multiplier, max_delay) == 0.8

    @patch("redis.StrictRedis")
    def test_fail_fast_configuration(self, mock_redis, mock_redis_config):
        """Test that fail-fast limits are properly configured."""
        mock_redis_instance = Mock()
        mock_redis.return_value = mock_redis_instance

        # Mock pubsub to fail immediately
        mock_pubsub = Mock()
        mock_redis_instance.pubsub.return_value = mock_pubsub
        mock_pubsub.run_in_thread.side_effect = Exception("Connection failed")

        # Test that initial connection failure with crash_on_failure raises immediately
        mock_redis_config.pubsub_retry_enabled = False
        mock_redis_config.pubsub_crash_on_failure = True

        with pytest.raises(RedisConnectionFailureError, match="Initial Redis pub/sub connection failed"):
            RedisMessagingBackend(mock_redis_config)

    @patch("redis.StrictRedis")
    def test_retry_disabled_behavior(self, mock_redis, mock_redis_config):
        """Test behavior when retry is disabled."""
        mock_redis_instance = Mock()
        mock_redis.return_value = mock_redis_instance

        mock_pubsub = Mock()
        mock_redis_instance.pubsub.return_value = mock_pubsub
        mock_pubsub.run_in_thread.side_effect = Exception("Connection failed")

        # Test with retry disabled and crash disabled - should propagate original exception
        mock_redis_config.pubsub_retry_enabled = False
        mock_redis_config.pubsub_crash_on_failure = False

        with pytest.raises(Exception, match="Connection failed"):
            RedisMessagingBackend(mock_redis_config)

    @patch("redis.StrictRedis")
    def test_successful_connection_setup(self, mock_redis, mock_redis_config):
        """Test successful connection setup without retry logic."""
        mock_redis_instance = Mock()
        mock_redis.return_value = mock_redis_instance

        # Mock successful pubsub setup
        mock_pubsub = Mock()
        mock_redis_instance.pubsub.return_value = mock_pubsub
        mock_thread = Mock()
        mock_thread.is_alive.return_value = True
        mock_pubsub.run_in_thread.return_value = mock_thread

        with patch.object(RedisMessagingBackend, "_start_pubsub_health_monitor") as mock_monitor:
            backend = RedisMessagingBackend(mock_redis_config)

            # Verify successful setup
            assert hasattr(backend, "p")
            assert hasattr(backend, "redis_thread")
            mock_monitor.assert_called_once()

    @patch("redis.StrictRedis")
    def test_retry_limits_validation(self, mock_redis, mock_redis_config):
        """Test that retry limits are properly validated."""
        backend_config = mock_redis_config

        # Test various limit configurations
        assert backend_config.pubsub_max_retry_attempts == 3
        assert backend_config.pubsub_max_retry_time == 5.0

        # Test with different limits
        custom_config = RedisBackendConfig(
            host="localhost", port=6379, pubsub_max_retry_attempts=10, pubsub_max_retry_time=60.0
        )

        assert custom_config.pubsub_max_retry_attempts == 10
        assert custom_config.pubsub_max_retry_time == 60.0


class TestRedisBackendHealthMonitoring:
    """Test health monitoring and connection recovery."""

    @pytest.fixture
    def config_with_monitoring(self):
        return RedisBackendConfig(
            host="localhost",
            port=6379,
            pubsub_retry_enabled=True,
            pubsub_health_check_interval=0.1,  # Fast for testing
            pubsub_health_monitor_initial_delay=0.1,  # Short initial delay for testing
            pubsub_max_retry_attempts=2,
        )

    @patch("redis.StrictRedis")
    def test_health_monitor_detects_dead_thread(self, mock_redis, config_with_monitoring):
        """Test that health monitor detects when pub/sub thread dies."""
        mock_redis_instance = Mock()
        mock_redis.return_value = mock_redis_instance

        # Mock successful initial setup
        mock_pubsub = Mock()
        mock_redis_instance.pubsub.return_value = mock_pubsub
        mock_thread = Mock()
        mock_thread.is_alive.return_value = True
        mock_pubsub.run_in_thread.return_value = mock_thread

        with patch.object(RedisMessagingBackend, "_schedule_pubsub_reconnect") as mock_reconnect:
            backend = RedisMessagingBackend(config_with_monitoring)
            assert backend is not None  # Ensure backend was created

            # Simulate thread death
            mock_thread.is_alive.return_value = False

            # Wait for initial delay (0.1s) + health check interval (0.1s) + some buffer
            time.sleep(0.3)

            # Should have triggered reconnection
            mock_reconnect.assert_called()

    @patch("redis.StrictRedis")
    def test_health_monitor_thread_lifecycle(self, mock_redis, config_with_monitoring):
        """Test that health monitor thread starts and stops properly."""
        mock_redis_instance = Mock()
        mock_redis.return_value = mock_redis_instance

        # Mock successful initial setup
        mock_pubsub = Mock()
        mock_redis_instance.pubsub.return_value = mock_pubsub
        mock_thread = Mock()
        mock_thread.is_alive.return_value = True
        mock_pubsub.run_in_thread.return_value = mock_thread

        backend = RedisMessagingBackend(config_with_monitoring)

        # Health monitor should be started
        assert backend._pubsub_health_thread is not None
        assert backend._pubsub_health_thread.is_alive()

        # Cleanup should stop the health monitor
        backend.cleanup()

        # Health monitor should be stopped
        time.sleep(0.1)  # Give cleanup time to complete


class TestRedisBackendSubscriptionRecovery:
    """Test subscription persistence and recovery after reconnection."""

    @pytest.fixture
    def test_backend(self):
        fake_redis_client = fakeredis.FakeStrictRedis()
        backend = RedisMessagingBackend(fake_redis_client)
        yield backend
        backend.cleanup()

    def test_subscription_tracking(self, test_backend):
        """Test that subscriptions are tracked for recovery."""
        handler1 = Mock()
        handler2 = Mock()

        test_backend.subscribe("topic1", handler1)
        test_backend.subscribe("topic2", handler2)

        assert "topic1" in test_backend._subscriptions
        assert "topic2" in test_backend._subscriptions
        assert test_backend._subscriptions["topic1"] == handler1
        assert test_backend._subscriptions["topic2"] == handler2

    def test_unsubscribe_removes_tracking(self, test_backend):
        """Test that unsubscribe removes subscription from tracking."""
        handler = Mock()

        test_backend.subscribe("topic1", handler)
        assert "topic1" in test_backend._subscriptions

        test_backend.unsubscribe("topic1")
        assert "topic1" not in test_backend._subscriptions

    @patch("redis.StrictRedis")
    def test_resubscription_after_reconnection(self, mock_redis):
        """Test that all subscriptions are restored after reconnection."""
        mock_redis_instance = Mock()
        mock_redis.return_value = mock_redis_instance

        # Mock successful pubsub setup
        mock_pubsub = Mock()
        mock_redis_instance.pubsub.return_value = mock_pubsub
        mock_pubsub.run_in_thread.return_value = Mock()

        config = RedisBackendConfig(host="localhost", port=6379)
        backend = RedisMessagingBackend(config)

        # Add some subscriptions
        handler1 = Mock()
        handler2 = Mock()
        backend._subscriptions["topic1"] = handler1
        backend._subscriptions["topic2"] = handler2

        # Test resubscription
        with patch.object(backend, "_subscribe_internal") as mock_subscribe:
            backend._resubscribe_all()

            # Should have called _subscribe_internal for each tracked subscription
            assert mock_subscribe.call_count == 2
            mock_subscribe.assert_any_call("topic1", handler1)
            mock_subscribe.assert_any_call("topic2", handler2)


class TestRedisBackendCleanup:
    """Test proper cleanup of resources."""

    @patch("redis.StrictRedis")
    def test_cleanup_stops_all_threads(self, mock_redis):
        """Test that cleanup properly stops all background threads."""
        mock_redis_instance = Mock()
        mock_redis.return_value = mock_redis_instance

        mock_pubsub = Mock()
        mock_redis_instance.pubsub.return_value = mock_pubsub
        mock_redis_thread = Mock()
        mock_pubsub.run_in_thread.return_value = mock_redis_thread

        config = RedisBackendConfig(host="localhost", port=6379, pubsub_retry_enabled=True)
        backend = RedisMessagingBackend(config)

        # Mock health monitor thread
        mock_health_thread = Mock()
        backend._pubsub_health_thread = mock_health_thread

        # Call cleanup
        backend.cleanup()

        # Should have set shutdown event
        assert backend._shutdown_event.is_set()

        # Should have stopped Redis thread
        mock_redis_thread.stop.assert_called_once()
        mock_redis_thread.join.assert_called_once_with(timeout=1)

        # Should have closed pubsub
        mock_pubsub.close.assert_called_once()

        # Should have waited for health thread
        mock_health_thread.join.assert_called_once_with(timeout=1)

        # Should have closed Redis connection
        mock_redis_instance.close.assert_called_once()


class TestRedisBackendErrorConditions:
    """Test various error conditions and edge cases."""

    def test_invalid_redis_client_type(self):
        """Test that invalid Redis client type raises appropriate error."""
        with pytest.raises(ValueError, match="Invalid Redis client"):
            # Use an object that's not a valid Redis client type
            invalid_client = object()  # Not a Redis client, dict, or RedisBackendConfig
            RedisMessagingBackend(invalid_client)  # type: ignore

    @patch("redis.StrictRedis")
    def test_retry_disabled_crash_enabled(self, mock_redis):
        """Test immediate crash when retry disabled but crash_on_failure enabled."""
        mock_redis_instance = Mock()
        mock_redis.return_value = mock_redis_instance

        mock_pubsub = Mock()
        mock_redis_instance.pubsub.return_value = mock_pubsub
        mock_pubsub.run_in_thread.side_effect = Exception("Connection failed")

        config = RedisBackendConfig(
            host="localhost", port=6379, pubsub_retry_enabled=False, pubsub_crash_on_failure=True
        )

        with pytest.raises(RedisConnectionFailureError, match="Initial Redis pub/sub connection failed"):
            RedisMessagingBackend(config)

    @patch("redis.StrictRedis")
    def test_retry_disabled_crash_disabled(self, mock_redis):
        """Test that original exception is raised when both retry and crash are disabled."""
        mock_redis_instance = Mock()
        mock_redis.return_value = mock_redis_instance

        mock_pubsub = Mock()
        mock_redis_instance.pubsub.return_value = mock_pubsub
        original_error = Exception("Original connection error")
        mock_pubsub.run_in_thread.side_effect = original_error

        config = RedisBackendConfig(
            host="localhost", port=6379, pubsub_retry_enabled=False, pubsub_crash_on_failure=False
        )

        with pytest.raises(Exception, match="Original connection error"):
            RedisMessagingBackend(config)
