import pytest

from rustic_ai.core.messaging import MessagingConfig

from ..core.base_test_messaging import BaseTestMessagingABC


class TestMessagingWithInMemoryStorage(BaseTestMessagingABC):
    @pytest.fixture
    def messaging_config(self) -> MessagingConfig:
        """
        Fixture that returns an instance of the InMemoryStorage implementation.
        """
        return MessagingConfig(
            backend_module="rustic_ai.core.messaging",
            backend_class="InMemoryMessagingBackend",
            backend_config={},
        )

    @pytest.fixture
    def namespace(self):
        return "test_in_memory"
