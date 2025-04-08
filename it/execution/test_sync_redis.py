import pytest

from rustic_ai.core.messaging.core.messaging_config import MessagingConfig
from rustic_ai.redis.messaging.backend import RedisBackendConfig

from core.tests.integration.execution.base_test_integration import IntegrationTestABC


class TestSyncRedisIntegration(IntegrationTestABC):
    @pytest.fixture
    def messaging(self, guild_id):
        redis_config = RedisBackendConfig(host="localhost", port=6379, ssl=False)
        messaging = MessagingConfig(
            backend_module="rustic_ai.redis.messaging.backend",
            backend_class="RedisMessagingBackend",
            backend_config={"redis_client": redis_config},
        )
        yield messaging

    @pytest.fixture
    def execution_engine(self) -> str:
        return "rustic_ai.core.guild.execution.sync.SyncExecutionEngine"
