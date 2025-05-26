import pathlib

import pytest
import ray

from rustic_ai.core.messaging.core.messaging_config import MessagingConfig
from rustic_ai.redis.messaging.backend import RedisBackendConfig

from rustic_ai.testing.execution.base_test_integration import IntegrationTestABC

# Get the directory of the current test file
WORKING_DIR_ROOT = pathlib.Path(__file__).parent.parent.resolve()


class TestRayRedisIntegration(IntegrationTestABC):
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
    def execution_engine(self):
        ray.init(include_dashboard=True, runtime_env={"working_dir": str(WORKING_DIR_ROOT)})
        yield "rustic_ai.ray.execution.RayExecutionEngine"
        ray.shutdown()
