import pytest

from rustic_ai.core.state.manager.in_memory_state_manager import InMemoryStateManager
from rustic_ai.core.state.models import (
    StateFetchRequest,
    StateOwner,
    StateUpdateFormat,
    StateUpdateRequest,
)


class TestStateManagerNestedPaths:
    """
    Test cases specifically for creating nested paths in empty states.
    This prevents regression of the issue where JsonUtils.update_at_path()
    couldn't create intermediate structures in empty states.
    """

    @pytest.fixture
    def state_manager(self) -> InMemoryStateManager:
        return InMemoryStateManager()

    def test_create_nested_path_in_empty_guild_state(self, state_manager: InMemoryStateManager):
        """Test creating a nested path like 'agents.health' in an empty guild state."""
        # Start with completely empty state (no init_from_state call)
        guild_id = "TEST_GUILD"

        # Try to update a nested path that doesn't exist
        request = StateUpdateRequest(
            state_owner=StateOwner.GUILD,
            guild_id=guild_id,
            update_path="agents.health",
            update_format=StateUpdateFormat.JSON_MERGE_PATCH,
            state_update={"agent1": {"checktime": "2025-01-01T00:00:00", "checkstatus": "ok", "checkmeta": {}}},
        )

        # This should not fail and should create the nested structure
        result = state_manager.update_state(request)

        # Verify the nested structure was created correctly
        expected_state = {
            "agents": {"health": {"agent1": {"checktime": "2025-01-01T00:00:00", "checkstatus": "ok", "checkmeta": {}}}}
        }

        assert result.state == expected_state
        assert result.version == 1

        # Verify we can fetch the nested data back
        fetch_request = StateFetchRequest(state_owner=StateOwner.GUILD, guild_id=guild_id, state_path="agents.health")

        fetch_result = state_manager.get_state(fetch_request)
        assert fetch_result.state == {
            "agent1": {"checktime": "2025-01-01T00:00:00", "checkstatus": "ok", "checkmeta": {}}
        }

    def test_create_nested_path_in_empty_agent_state(self, state_manager: InMemoryStateManager):
        """Test creating a nested path in an empty agent state."""
        guild_id = "TEST_GUILD"
        agent_id = "TEST_AGENT"

        # Try to update a nested path for an agent
        request = StateUpdateRequest(
            state_owner=StateOwner.AGENT,
            guild_id=guild_id,
            agent_id=agent_id,
            update_path="metrics.performance",
            update_format=StateUpdateFormat.JSON_MERGE_PATCH,
            state_update={"cpu_usage": 0.75, "memory_usage": 0.60},
        )

        result = state_manager.update_state(request)

        expected_state = {"metrics": {"performance": {"cpu_usage": 0.75, "memory_usage": 0.60}}}

        assert result.state == expected_state
        assert result.version == 1

    def test_create_deeply_nested_path(self, state_manager: InMemoryStateManager):
        """Test creating a deeply nested path like 'level1.level2.level3.data'."""
        guild_id = "TEST_GUILD"

        request = StateUpdateRequest(
            state_owner=StateOwner.GUILD,
            guild_id=guild_id,
            update_path="level1.level2.level3.data",
            update_format=StateUpdateFormat.JSON_MERGE_PATCH,
            state_update={"value": "deep_nested_value"},
        )

        result = state_manager.update_state(request)

        expected_state = {"level1": {"level2": {"level3": {"data": {"value": "deep_nested_value"}}}}}

        assert result.state == expected_state

    def test_update_existing_nested_path_still_works(self, state_manager: InMemoryStateManager):
        """Test that updating existing nested paths still works as before."""
        guild_id = "TEST_GUILD"

        # First create the nested structure
        request1 = StateUpdateRequest(
            state_owner=StateOwner.GUILD,
            guild_id=guild_id,
            update_path="agents.health",
            update_format=StateUpdateFormat.JSON_MERGE_PATCH,
            state_update={"agent1": {"status": "starting"}},
        )

        state_manager.update_state(request1)

        # Now update the existing nested path
        request2 = StateUpdateRequest(
            state_owner=StateOwner.GUILD,
            guild_id=guild_id,
            update_path="agents.health",
            update_format=StateUpdateFormat.JSON_MERGE_PATCH,
            state_update={"agent1": {"status": "running"}, "agent2": {"status": "starting"}},
        )

        result = state_manager.update_state(request2)

        expected_state = {"agents": {"health": {"agent1": {"status": "running"}, "agent2": {"status": "starting"}}}}

        assert result.state == expected_state
        assert result.version == 2  # Should be version 2 after second update

    # Tests to verify that JsonUtils.update_at_path can handle empty states with JSON_PATCH
    def test_update_empty_state(self, state_manager: InMemoryStateManager):
        """Test updating an empty state with a JSON Patch operation."""
        guild_id = "TEST_GUILD"
        agent_id = "TEST_AGENT"

        request = StateUpdateRequest(
            state_owner=StateOwner.AGENT,
            guild_id=guild_id,
            agent_id=agent_id,
            update_path="metrics",
            update_format=StateUpdateFormat.JSON_PATCH,
            state_update={
                "operations": [
                    {
                        "op": "add",
                        "path": "/performance",
                        "value": {"cpu_usage": 0.75, "memory_usage": 0.60},
                    }
                ]
            },
        )

        result = state_manager.update_state(request)

        expected_state = {"metrics": {"performance": {"cpu_usage": 0.75, "memory_usage": 0.60}}}

        assert result.state == expected_state
        assert result.version == 1
