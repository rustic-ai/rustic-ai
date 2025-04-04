import pytest
from core.tests.guild.agent_ext.depends.test_di_kvstore import BaseTestKVStore

from rustic_ai.core.guild.agent_ext.depends.dependency_resolver import DependencySpec
from rustic_ai.redis.agent_ext.redis_kvstore import RedisKVStoreResolver


class TestRedisKVStore(BaseTestKVStore):
    @pytest.fixture
    def dep_map(self) -> dict:
        return {
            "kvstore": DependencySpec(
                class_name=RedisKVStoreResolver.get_qualified_class_name(),
                properties={"host": "localhost", "port": 6379},
            )
        }
