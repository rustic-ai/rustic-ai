import fakeredis
import pytest

from rustic_ai.redis.messaging.backend import RedisMessagingBackend

from rustic_ai.testing.messaging.base_test_backend import BaseTestBackendABC


class TestRedisBackend(BaseTestBackendABC):
    @pytest.fixture
    def backend(self):
        """Fixture that returns an instance of RedisStorage."""
        fake_redis_client = fakeredis.FakeStrictRedis()
        storage = RedisMessagingBackend(fake_redis_client)
        yield storage
        storage.cleanup()
