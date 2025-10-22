"""Pytest configuration for k8s module tests."""

import pytest
import redis
import fakeredis


@pytest.fixture
def redis_client():
    """Provide a fake Redis client for testing."""
    return fakeredis.FakeRedis(decode_responses=True)
