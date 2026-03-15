"""Tests for the messaging bus using NATS storage backend."""

import pytest

from rustic_ai.core.messaging.core.messaging_config import MessagingConfig

from rustic_ai.testing.messaging.base_test_messaging import BaseTestMessagingABC


class TestMessagingBusWithNATSStorage(BaseTestMessagingABC):
    """Inherits 15 tests from BaseTestMessagingABC."""

    @pytest.fixture
    def messaging_config(self, nats_url):
        """Return a MessagingConfig using the NATSMessagingBackend."""
        return MessagingConfig(
            backend_module="rustic_ai.nats.messaging.backend",
            backend_class="NATSMessagingBackend",
            backend_config={
                "nats_client": {
                    "servers": [nats_url],
                    "pubsub_health_monitoring_enabled": False,
                }
            },
        )

    @pytest.fixture
    def namespace(self):
        """Use a unique namespace per test to avoid stream accumulation across tests."""
        import uuid

        return f"test_nats_{uuid.uuid4().hex[:8]}"
