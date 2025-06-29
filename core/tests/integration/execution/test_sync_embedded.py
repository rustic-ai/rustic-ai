import pytest

from rustic_ai.core.messaging.core.messaging_config import MessagingConfig

from .base_test_integration import IntegrationTestABC


class TestSyncEmbeddedIntegration(IntegrationTestABC):
    """Integration tests for sync execution with EmbeddedMessagingBackend.

    This tests the EmbeddedMessagingBackend's behavior in synchronous execution
    scenarios, ensuring consistent behavior across all execution modes.
    """

    @pytest.fixture
    def messaging(self, guild_id) -> MessagingConfig:
        return MessagingConfig(
            backend_module="rustic_ai.core.messaging.backend.embedded_backend",
            backend_class="EmbeddedMessagingBackend",
            backend_config={"auto_start_server": True},
        )

    @pytest.fixture
    def execution_engine(self) -> str:
        return "rustic_ai.core.guild.execution.sync.SyncExecutionEngine"
