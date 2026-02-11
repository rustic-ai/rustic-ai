from abc import ABC, abstractmethod
import os
import uuid

import pytest

from rustic_ai.core.messaging import JsonDict
from rustic_ai.core.state.manager.state_manager import StateManager
from rustic_ai.core.state.models import (
    StateFetchRequest,
    StateOwner,
    StateUpdateFormat,
    StateUpdateRequest,
)


class BaseTestStateManager(ABC):

    @pytest.fixture
    @abstractmethod
    def state_manager(self, request) -> StateManager:
        """
        Fixture that returns StateManager Implementation being tested.
        This should be overridden in subclasses that test specific StateManager implementations.
        """
        raise NotImplementedError("This fixture should be overridden in subclasses.")

    @pytest.fixture
    def guild_id(self, request) -> str:
        worker_id = os.environ.get("PYTEST_XDIST_WORKER", "master")
        node_id = request.node.nodeid.replace("/", "_").replace(":", "_").replace("[", "_").replace("]", "_")
        return f"test_guild_{worker_id}_{node_id}_{uuid.uuid4().hex[:8]}"

    @pytest.fixture
    def agent_id(self, request) -> str:
        worker_id = os.environ.get("PYTEST_XDIST_WORKER", "master")
        node_id = request.node.nodeid.replace("/", "_").replace(":", "_").replace("[", "_").replace("]", "_")
        return f"test_agent_{worker_id}_{node_id}_{uuid.uuid4().hex[:8]}"

    @pytest.fixture
    def base_state(self, guild_id: str, agent_id: str) -> JsonDict:
        return {
            guild_id: {
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
            f"{guild_id}#{agent_id}": {
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
            {"state_owner": StateOwner.GUILD},
            {
                "some": {
                    "key1": "value1",
                    "key2": "value2",
                    "nkey": {
                        "nkey1": "nvalue1",
                        "nkey2": "nvalue2",
                    },
                }
            },
            id="FetchGuildState",
        ),
        pytest.param(
            {"state_owner": StateOwner.GUILD, "state_path": "some.key1"},
            {"key1": "value1"},
            id="FetchGuildStatePath",
        ),
        pytest.param(
            {"state_owner": StateOwner.GUILD, "state_path": "some.nkey.nkey1"},
            {"nkey1": "nvalue1"},
            id="FetchGuildStateNestedPath",
        ),
        pytest.param(
            {"state_owner": StateOwner.AGENT},
            {
                "other": {
                    "key1": "value1",
                    "key2": "value2",
                }
            },
            id="FetchAgentState",
        ),
        pytest.param(
            {"state_owner": StateOwner.AGENT, "state_path": "other.key1"},
            {"key1": "value1"},
            id="FetchAgentStatePath",
        ),
    ]

    @pytest.mark.parametrize("sfr, expected_response", state_fetch_data)
    def test_get_state(
        self,
        state_manager: StateManager,
        base_state: JsonDict,
        guild_id: str,
        agent_id: str,
        sfr,
        expected_response,
    ):
        state_manager.load(base_state)
        request = StateFetchRequest(
            state_owner=sfr["state_owner"],
            guild_id=guild_id,
            agent_id=agent_id if sfr["state_owner"] == StateOwner.AGENT else None,
            state_path=sfr.get("state_path"),
        )
        assert state_manager.get_state(request).state == expected_response

    state_update_data = [
        pytest.param(
            {
                "state_owner": StateOwner.GUILD,
                "update_format": StateUpdateFormat.JSON_MERGE_PATCH,
                "state_update": {"some": {"key1": "new_value"}},
            },
            {
                "some": {
                    "key1": "new_value",
                    "key2": "value2",
                    "nkey": {
                        "nkey1": "nvalue1",
                        "nkey2": "nvalue2",
                    },
                },
            },
            id="MergePatchGuildState",
        ),
        pytest.param(
            {
                "state_owner": StateOwner.GUILD,
                "update_format": StateUpdateFormat.JSON_MERGE_PATCH,
                "state_update": {
                    "some": {
                        "key1": "new_value",
                        "key3": "value3",
                        "nkey": {
                            "nkey1": "new_nvalue1",
                        },
                    },
                },
            },
            {
                "some": {
                    "key1": "new_value",
                    "key2": "value2",
                    "key3": "value3",
                    "nkey": {
                        "nkey1": "new_nvalue1",
                        "nkey2": "nvalue2",
                    },
                },
            },
            id="MergePatchGuildStateNested",
        ),
        pytest.param(
            {
                "state_owner": StateOwner.GUILD,
                "update_format": StateUpdateFormat.JSON_PATCH,
                "state_update": {
                    "operations": [
                        {"op": "replace", "path": "/some/key1", "value": "new_value"},
                    ]
                },
            },
            {
                "some": {
                    "key1": "new_value",
                    "key2": "value2",
                    "nkey": {
                        "nkey1": "nvalue1",
                        "nkey2": "nvalue2",
                    },
                },
            },
            id="JsonPatchGuildState",
        ),
        pytest.param(
            {
                "state_owner": StateOwner.AGENT,
                "update_format": StateUpdateFormat.JSON_PATCH,
                "state_update": {
                    "operations": [
                        {"op": "replace", "path": "/other/key1", "value": "new_value"},
                        {"op": "add", "path": "/other/key3", "value": "value3"},
                    ]
                },
            },
            {
                "other": {
                    "key1": "new_value",
                    "key2": "value2",
                    "key3": "value3",
                },
            },
            id="JsonPatchAgentState",
        ),
    ]

    @pytest.mark.parametrize("sur, expected_state", state_update_data)
    def test_update_state(
        self,
        state_manager: StateManager,
        base_state: JsonDict,
        guild_id: str,
        agent_id: str,
        sur,
        expected_state,
    ):
        state_manager.load(base_state)
        request = StateUpdateRequest(
            state_owner=sur["state_owner"],
            guild_id=guild_id,
            agent_id=agent_id if sur["state_owner"] == StateOwner.AGENT else None,
            update_format=sur["update_format"],
            state_update=sur["state_update"],
            update_path=sur.get("update_path"),
            update_version=sur.get("update_version"),
            update_timestamp=sur.get("update_timestamp"),
        )
        updated_state = state_manager.update_state(request)

        assert updated_state.state == expected_state
        assert updated_state.version == 1

        sfr = state_manager.get_state(
            StateFetchRequest(
                state_owner=request.state_owner,
                guild_id=request.guild_id,
                agent_id=request.agent_id,
                state_path=request.update_path,
                version=request.update_version,
                timestamp=request.update_timestamp,
            )
        )

        assert sfr.state == expected_state
