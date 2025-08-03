import pytest

from rustic_ai.core.state.manager.state_manager import StateManager
from rustic_ai.redis.state.manager import RedisStateManager

from rustic_ai.testing.state.base_test_state_mgr import BaseTestStateManager


class TestRedisStateManager(BaseTestStateManager):

    @pytest.fixture
    def state_manager(self, request) -> StateManager:
        return RedisStateManager(**{"host": "localhost", "port": 6379})
