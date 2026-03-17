import pytest

from rustic_ai.core.state.manager.diskcache_state_manager import DiskCacheStateManager
from rustic_ai.core.state.manager.state_manager import StateManager
from rustic_ai.core.state.models import (
    StateFetchRequest,
    StateOwner,
    StateUpdateFormat,
    StateUpdateRequest,
)


class TestDiskCacheStateManager:

    @pytest.fixture
    def state_manager(self, tmp_path) -> StateManager:
        return DiskCacheStateManager(cache_dir=str(tmp_path / "state_cache"))

    @pytest.fixture
    def base_state(self):
        return {
            "GUILD001": {
                "state": {
                    "some": {
                        "key1": "value1",
                        "key2": "value2",
                        "nkey": {
                            "nkey1": "nvalue1",
                            "nkey2": "nvalue2",
                        },
                    },
                },
                "version": 0,
                "timestamp": 0,
            },
            "GUILD001#AGENT001": {
                "state": {
                    "other": {
                        "key1": "value1",
                        "key2": "value2",
                    },
                },
                "version": 0,
                "timestamp": 0,
            },
        }

    state_fetch_data = [
        pytest.param(
            StateFetchRequest(state_owner=StateOwner.GUILD, guild_id="GUILD001"),
            {
                "some": {
                    "key1": "value1",
                    "key2": "value2",
                    "nkey": {"nkey1": "nvalue1", "nkey2": "nvalue2"},
                }
            },
            id="FetchGuildState",
        ),
        pytest.param(
            StateFetchRequest(state_owner=StateOwner.GUILD, guild_id="GUILD001", state_path="some.key1"),
            {"key1": "value1"},
            id="FetchGuildStatePath",
        ),
        pytest.param(
            StateFetchRequest(state_owner=StateOwner.GUILD, guild_id="GUILD001", state_path="some.nkey.nkey1"),
            {"nkey1": "nvalue1"},
            id="FetchGuildStateNestedPath",
        ),
        pytest.param(
            StateFetchRequest(state_owner=StateOwner.AGENT, guild_id="GUILD001", agent_id="AGENT001"),
            {"other": {"key1": "value1", "key2": "value2"}},
            id="FetchAgentState",
        ),
        pytest.param(
            StateFetchRequest(
                state_owner=StateOwner.AGENT, guild_id="GUILD001", agent_id="AGENT001", state_path="other.key1"
            ),
            {"key1": "value1"},
            id="FetchAgentStatePath",
        ),
    ]

    @pytest.mark.parametrize("sfr, expected_response", state_fetch_data)
    def test_get_state(self, state_manager: StateManager, base_state, sfr, expected_response):
        state_manager.load(base_state)
        assert state_manager.get_state(sfr).state == expected_response

    state_update_data = [
        pytest.param(
            StateUpdateRequest(
                state_owner=StateOwner.GUILD,
                guild_id="GUILD001",
                update_format=StateUpdateFormat.JSON_MERGE_PATCH,
                state_update={"some": {"key1": "new_value"}},
            ),
            {
                "some": {
                    "key1": "new_value",
                    "key2": "value2",
                    "nkey": {"nkey1": "nvalue1", "nkey2": "nvalue2"},
                },
            },
            id="MergePatchGuildState",
        ),
        pytest.param(
            StateUpdateRequest(
                state_owner=StateOwner.GUILD,
                guild_id="GUILD001",
                update_format=StateUpdateFormat.JSON_MERGE_PATCH,
                state_update={"some": {"key1": "new_value", "key3": "value3", "nkey": {"nkey1": "new_nvalue1"}}},
            ),
            {
                "some": {
                    "key1": "new_value",
                    "key2": "value2",
                    "key3": "value3",
                    "nkey": {"nkey1": "new_nvalue1", "nkey2": "nvalue2"},
                },
            },
            id="MergePatchGuildStateNested",
        ),
        pytest.param(
            StateUpdateRequest(
                state_owner=StateOwner.GUILD,
                guild_id="GUILD001",
                update_format=StateUpdateFormat.JSON_PATCH,
                state_update={"operations": [{"op": "replace", "path": "/some/key1", "value": "new_value"}]},
            ),
            {
                "some": {
                    "key1": "new_value",
                    "key2": "value2",
                    "nkey": {"nkey1": "nvalue1", "nkey2": "nvalue2"},
                },
            },
            id="JsonPatchGuildState",
        ),
        pytest.param(
            StateUpdateRequest(
                state_owner=StateOwner.AGENT,
                guild_id="GUILD001",
                agent_id="AGENT001",
                update_format=StateUpdateFormat.JSON_PATCH,
                state_update={
                    "operations": [
                        {"op": "replace", "path": "/other/key1", "value": "new_value"},
                        {"op": "add", "path": "/other/key3", "value": "value3"},
                    ]
                },
            ),
            {"other": {"key1": "new_value", "key2": "value2", "key3": "value3"}},
            id="JsonPatchAgentState",
        ),
    ]

    @pytest.mark.parametrize("sur, expected_state", state_update_data)
    def test_update_state(self, state_manager: StateManager, base_state, sur: StateUpdateRequest, expected_state):
        state_manager.load(base_state)
        updated_state = state_manager.update_state(sur)

        assert updated_state.state == expected_state
        assert updated_state.version == 1

        sfr = state_manager.get_state(
            StateFetchRequest(
                state_owner=sur.state_owner,
                guild_id=sur.guild_id,
                agent_id=sur.agent_id,
                state_path=sur.update_path,
                version=sur.update_version,
                timestamp=sur.update_timestamp,
            )
        )
        assert sfr.state == expected_state


class TestDiskCacheStateManagerEdgeCases:

    def test_missing_cache_dir_raises(self):
        with pytest.raises(ValueError, match="cache_dir"):
            DiskCacheStateManager()

    def test_empty_cache_dir_raises(self):
        with pytest.raises(ValueError, match="cache_dir"):
            DiskCacheStateManager(cache_dir="")

    def test_persistence_across_instances(self, tmp_path):
        cache_dir = str(tmp_path / "persist_test")

        mgr1 = DiskCacheStateManager(cache_dir=cache_dir)
        mgr1.load(
            {
                "G1": {
                    "state": {"foo": "bar"},
                    "version": 3,
                    "timestamp": 100,
                }
            }
        )
        mgr1._cache.close()

        mgr2 = DiskCacheStateManager(cache_dir=cache_dir)
        details = mgr2._get_state_details("G1")
        assert details["state"] == {"foo": "bar"}
        assert details["version"] == 3
        assert details["timestamp"] == 100
        mgr2._cache.close()

    def test_get_nonexistent_key_returns_empty(self, tmp_path):
        mgr = DiskCacheStateManager(cache_dir=str(tmp_path / "empty_test"))
        details = mgr._get_state_details("does_not_exist")
        assert details == {"state": {}, "version": 0, "timestamp": 0}
        mgr._cache.close()
