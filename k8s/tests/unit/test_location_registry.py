"""Unit tests for AgentLocationRegistry."""

import pytest
import time
import fakeredis

from rustic_ai.k8s.registry.location_registry import AgentLocationRegistry


@pytest.fixture
def redis_client():
    """Provide a fake Redis client for testing."""
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def registry(redis_client):
    """Provide an AgentLocationRegistry instance."""
    return AgentLocationRegistry(redis_client)


class TestAgentLocationRegistry:
    """Test suite for AgentLocationRegistry."""

    def test_register_and_lookup(self, registry):
        """Test basic agent registration and lookup."""
        # Register agent
        registry.register("agent-1", "host-1:50051")

        # Lookup should return the location
        location = registry.get_location("agent-1")
        assert location == "host-1:50051"

    def test_register_multiple_agents(self, registry):
        """Test registering multiple agents on different hosts."""
        registry.register("agent-1", "host-1:50051")
        registry.register("agent-2", "host-2:50051")
        registry.register("agent-3", "host-1:50051")

        assert registry.get_location("agent-1") == "host-1:50051"
        assert registry.get_location("agent-2") == "host-2:50051"
        assert registry.get_location("agent-3") == "host-1:50051"

    def test_lookup_nonexistent_agent(self, registry):
        """Test looking up an agent that doesn't exist."""
        location = registry.get_location("nonexistent")
        assert location is None

    def test_heartbeat_existing_agent(self, registry):
        """Test heartbeat refreshes TTL for existing agent."""
        registry.register("agent-1", "host-1:50051")

        # Heartbeat should succeed
        result = registry.heartbeat("agent-1")
        assert result is True

    def test_heartbeat_nonexistent_agent(self, registry):
        """Test heartbeat fails for nonexistent agent."""
        result = registry.heartbeat("nonexistent")
        assert result is False

    def test_deregister_agent(self, registry):
        """Test deregistering an agent."""
        # Register
        registry.register("agent-1", "host-1:50051")
        assert registry.get_location("agent-1") == "host-1:50051"

        # Deregister
        registry.deregister("agent-1")

        # Should no longer be found
        assert registry.get_location("agent-1") is None

    def test_deregister_removes_from_host_set(self, registry):
        """Test that deregister removes agent from host set."""
        registry.register("agent-1", "host-1:50051")
        registry.register("agent-2", "host-1:50051")

        # Both should be in host set
        agents = registry.get_host_agents("host-1")
        assert set(agents) == {"agent-1", "agent-2"}

        # Deregister one
        registry.deregister("agent-1")

        # Only agent-2 should remain
        agents = registry.get_host_agents("host-1")
        assert agents == ["agent-2"]

    def test_get_host_load(self, registry):
        """Test getting agent count per host."""
        registry.register("agent-1", "host-1:50051")
        registry.register("agent-2", "host-1:50051")
        registry.register("agent-3", "host-2:50051")

        load = registry.get_host_load()
        assert load == {"host-1": 2, "host-2": 1}

    def test_get_host_load_empty(self, registry):
        """Test getting host load when no agents registered."""
        load = registry.get_host_load()
        assert load == {}

    def test_get_host_agents(self, registry):
        """Test getting all agents on a specific host."""
        registry.register("agent-1", "host-1:50051")
        registry.register("agent-2", "host-1:50051")
        registry.register("agent-3", "host-2:50051")

        agents = registry.get_host_agents("host-1")
        assert set(agents) == {"agent-1", "agent-2"}

        agents = registry.get_host_agents("host-2")
        assert agents == ["agent-3"]

    def test_get_host_agents_empty_host(self, registry):
        """Test getting agents from a host with no agents."""
        agents = registry.get_host_agents("nonexistent-host")
        assert agents == []

    def test_ttl_set_on_registration(self, registry, redis_client):
        """Test that TTL is set when registering an agent."""
        registry.register("agent-1", "host-1:50051")

        # Check TTL exists
        key = "agent_location:agent-1"
        ttl = redis_client.ttl(key)

        # TTL should be close to 60 seconds
        assert ttl > 0
        assert ttl <= 60

    def test_cleanup_dead_agents(self, registry, redis_client):
        """Test cleanup of agents with expired location entries."""
        # Register agents
        registry.register("agent-1", "host-1:50051")
        registry.register("agent-2", "host-1:50051")

        # Manually delete location for agent-1 (simulate TTL expiry)
        redis_client.delete("agent_location:agent-1")

        # Cleanup should remove agent-1 from host set
        cleaned = registry.cleanup_dead_agents()

        assert "agent-1" in cleaned
        assert "agent-2" not in cleaned

        # Verify agent-1 is removed from host set
        agents = registry.get_host_agents("host-1")
        assert agents == ["agent-2"]

    def test_register_overwrites_existing(self, registry):
        """Test that re-registering an agent updates its location."""
        registry.register("agent-1", "host-1:50051")
        assert registry.get_location("agent-1") == "host-1:50051"

        # Re-register with different host
        registry.register("agent-1", "host-2:50051")
        assert registry.get_location("agent-1") == "host-2:50051"

        # Old host should not have agent-1 anymore
        agents_host1 = registry.get_host_agents("host-1")
        assert "agent-1" not in agents_host1

        # New host should have agent-1
        agents_host2 = registry.get_host_agents("host-2")
        assert "agent-1" in agents_host2

    def test_multiple_heartbeats(self, registry):
        """Test multiple heartbeats keep agent alive."""
        registry.register("agent-1", "host-1:50051")

        # Multiple heartbeats should all succeed
        for _ in range(5):
            result = registry.heartbeat("agent-1")
            assert result is True

        # Agent should still be findable
        assert registry.get_location("agent-1") == "host-1:50051"
