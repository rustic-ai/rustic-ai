import pytest

from rustic_ai.core.messaging import InMemoryMessagingBackend

from ..core.base_test_backend import BaseTestBackendABC
from rustic_ai.testing.messaging.base_test_delivery_guarantees import (
    BaseTestBackendDeliveryGuarantees,
)


class TestInMemoryBackend(BaseTestBackendABC):
    @pytest.fixture
    def backend(self):
        """Fixture that returns an instance of InMemoryStorage."""
        inmem = InMemoryMessagingBackend()
        yield inmem
        inmem.cleanup()

    # No need to re-implement the test methods from TestStorageABC unless there's a specific behavior
    # of InMemoryStorage that needs to be tested differently.


class TestInMemoryDeliveryGuarantees(BaseTestBackendDeliveryGuarantees):
    @pytest.fixture
    def backend(self):
        inmem = InMemoryMessagingBackend()
        yield inmem
        inmem.cleanup()

    def test_backlog_replay(self, backend, generator, topic, namespace):
        super().test_backlog_replay(backend, generator, topic, namespace)

    def test_crash_recovery(self, backend, generator, topic, namespace):
        super().test_crash_recovery(backend, generator, topic, namespace)

    def test_handler_failure_no_position_advance(self, backend, generator, topic, namespace):
        super().test_handler_failure_no_position_advance(backend, generator, topic, namespace)
