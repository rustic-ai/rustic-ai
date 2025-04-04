import fakeredis
import pytest
from core.tests.messaging.core.base_test_backend import BaseTestBackendABC

from rustic_ai.redis.messaging.backend import RedisMessagingBackend


class TestRedisBackend(BaseTestBackendABC):
    @pytest.fixture
    def backend(self):
        """Fixture that returns an instance of RedisStorage."""
        fake_redis_client = fakeredis.FakeStrictRedis()
        storage = RedisMessagingBackend(fake_redis_client)
        yield storage
        storage.cleanup()
