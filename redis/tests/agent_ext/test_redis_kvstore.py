import pytest

from rustic_ai.core.guild.agent_ext.depends.dependency_resolver import DependencySpec
from rustic_ai.redis.agent_ext.kvstore import RedisKVStoreResolver

from rustic_ai.testing.agent_ext.base_test_kvstore import BaseTestKVStore


class TestRedisKVStore(BaseTestKVStore):
    @pytest.fixture
    def dep_map(self) -> dict:
        return {
            "kvstore": DependencySpec(
                class_name=RedisKVStoreResolver.get_qualified_class_name(),
                properties={"host": "localhost", "port": 6379},
            )
        }
