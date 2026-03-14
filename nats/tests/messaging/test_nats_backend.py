"""Tests for the NATSMessagingBackend."""

import uuid

import pytest

from rustic_ai.nats.messaging.backend import NATSMessagingBackend
from rustic_ai.nats.messaging.connection_manager import NATSBackendConfig

from rustic_ai.testing.messaging.base_test_backend import BaseTestBackendABC
from rustic_ai.testing.messaging.base_test_delivery_guarantees import (
    BaseTestBackendDeliveryGuarantees,
)


class TestNATSBackend(BaseTestBackendABC):
    """Inherits 8 tests from BaseTestBackendABC."""

    @pytest.fixture
    def backend(self, nats_url):
        """Fixture that returns an instance of NATSMessagingBackend."""
        config = NATSBackendConfig(
            servers=[nats_url],
            pubsub_health_monitoring_enabled=False,
        )
        storage = NATSMessagingBackend(config)
        yield storage
        storage.cleanup()

    @pytest.fixture
    def topic(self):
        """Use a unique topic per test to avoid stream accumulation across tests."""
        return f"test_topic_{uuid.uuid4().hex[:8]}"


class TestNATSDeliveryGuarantees(BaseTestBackendDeliveryGuarantees):
    """Delivery guarantee tests for NATS backend."""

    @pytest.fixture
    def backend(self, nats_url):
        config = NATSBackendConfig(
            servers=[nats_url],
            pubsub_health_monitoring_enabled=False,
        )
        storage = NATSMessagingBackend(config)
        yield storage
        storage.cleanup()

    @pytest.fixture
    def topic(self) -> str:
        return f"dg_topic_{uuid.uuid4().hex[:8]}"

    @pytest.fixture
    def namespace(self) -> str:
        return f"dg_ns_{uuid.uuid4().hex[:8]}"

    def test_handler_failure_no_position_advance(self, backend, generator, topic, namespace):
        super().test_handler_failure_no_position_advance(backend, generator, topic, namespace)


class TestNATSBackendConfiguration:
    """Test NATS backend configuration and initialization."""

    def test_default_configuration(self):
        """Test that default configuration values are set correctly."""
        config = NATSBackendConfig()

        assert config.servers == ["nats://localhost:4222"]
        assert config.tls is False
        assert config.connect_timeout == 10.0
        assert config.reconnect_time_wait == 2.0
        assert config.max_reconnect_attempts == -1
        assert config.ping_interval == 120
        assert config.max_outstanding_pings == 2
        assert config.message_ttl == 3600

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
        config = NATSBackendConfig(
            servers=["nats://myserver:4222"],
            name="test-client",
            tls=False,
            connect_timeout=5.0,
            pubsub_retry_enabled=False,
            pubsub_max_retry_attempts=3,
            pubsub_crash_on_failure=False,
            message_ttl=7200,
        )

        assert config.servers == ["nats://myserver:4222"]
        assert config.name == "test-client"
        assert config.connect_timeout == 5.0
        assert config.pubsub_retry_enabled is False
        assert config.pubsub_max_retry_attempts == 3
        assert config.pubsub_crash_on_failure is False
        assert config.message_ttl == 7200


class TestNATSBackendBasicFunctionality:
    """Test basic backend functionality through the public interface."""

    @pytest.fixture
    def test_backend(self, nats_url):
        """Create a test backend."""
        config = NATSBackendConfig(
            servers=[nats_url],
            pubsub_health_monitoring_enabled=False,
        )
        backend = NATSMessagingBackend(config)
        yield backend
        backend.cleanup()

    def test_configuration_access(self, test_backend):
        """Test that configuration can be accessed for testing purposes."""
        config = test_backend._config
        assert config is not None
        assert isinstance(config, NATSBackendConfig)

    def test_supports_subscription(self, test_backend):
        """Test that backend reports subscription support."""
        assert test_backend.supports_subscription() is True

    def test_subscription_basic_operations(self, test_backend):
        """Test basic subscribe/unsubscribe operations."""
        from unittest.mock import Mock

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


class TestNATSBackendErrorConditions:
    """Test error conditions and edge cases."""

    def test_invalid_client_type(self):
        """Test that an invalid client type raises ValueError."""
        with pytest.raises(ValueError):
            NATSMessagingBackend(object())  # type: ignore
