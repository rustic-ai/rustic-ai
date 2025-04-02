import pytest

from rustic_ai.core.messaging.core.messaging_config import MessagingConfig

from .base_test_integration import IntegrationTestABC


class TestMultiThreadedInMemoryIntegration(IntegrationTestABC):
    @pytest.fixture
    def messaging(self, guild_id) -> MessagingConfig:
        return MessagingConfig(
            backend_module="rustic_ai.core.messaging.backend",
            backend_class="InMemoryMessagingBackend",
            backend_config={},
        )

    @pytest.fixture
    def execution_engine(self) -> str:
        return "rustic_ai.core.guild.execution.multithreaded.MultiThreadedEngine"
