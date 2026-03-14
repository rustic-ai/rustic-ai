"""Tests for NATSKVStore."""

import os

import pytest

from rustic_ai.core.guild.agent_ext.depends.dependency_resolver import DependencySpec
from rustic_ai.nats.agent_ext.kvstore import NATSKVStoreResolver

from rustic_ai.testing.agent_ext.base_test_kvstore import BaseTestKVStore


class TestNATSKVStore(BaseTestKVStore):
    @pytest.fixture
    def dep_map(self) -> dict:
        nats_url = os.environ.get("NATS_URL", "nats://localhost:4222")
        return {
            "kvstore": DependencySpec(
                class_name=NATSKVStoreResolver.get_qualified_class_name(),
                properties={"servers": [nats_url]},
            )
        }
