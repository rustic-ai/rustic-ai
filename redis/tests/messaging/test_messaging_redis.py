import fakeredis
import pytest
from core.tests.messaging.core.base_test_messaging import BaseTestMessagingABC

from rustic_ai.core.messaging.core.messaging_config import MessagingConfig


class TestMessagingBusWithRedisStorage(BaseTestMessagingABC):
    @pytest.fixture
    def messaging_config(self):
        """
        Fixture that returns an instance of the RedisStorage implementation.
        """
        fake_redis_client = fakeredis.FakeStrictRedis()

        return MessagingConfig(
            backend_module="rustic_ai.redis.messaging.backend",
            backend_class="RedisMessagingBackend",
            backend_config={"redis_client": fake_redis_client},
        )

    @pytest.fixture
    def namespace(self):
        return "test_redis"
