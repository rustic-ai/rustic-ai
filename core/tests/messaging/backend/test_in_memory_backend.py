import pytest

from rustic_ai.core.messaging import InMemoryMessagingBackend

from ..core.base_test_backend import BaseTestBackendABC


class TestInMemoryBackend(BaseTestBackendABC):
    @pytest.fixture
    def backend(self):
        """Fixture that returns an instance of InMemoryStorage."""
        inmem = InMemoryMessagingBackend()
        yield inmem
        inmem.cleanup()

    # No need to re-implement the test methods from TestStorageABC unless there's a specific behavior
    # of InMemoryStorage that needs to be tested differently.
