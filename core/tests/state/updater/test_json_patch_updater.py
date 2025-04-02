import pytest

from rustic_ai.core.messaging import JsonDict
from rustic_ai.core.state.updater.json_patch_updater import JsonPatchUpdater


class TestJsonPatchUpdater:
    @pytest.fixture
    def state(self) -> JsonDict:
        return {"name": "John", "age": 30, "city": "New York"}

    @pytest.fixture
    def update(self) -> JsonDict:
        return {
            "operations": [
                {"op": "replace", "path": "/age", "value": 31},
                {"op": "add", "path": "/married", "value": True},
            ]
        }

    @pytest.fixture
    def updated_state(self) -> JsonDict:
        return {"name": "John", "age": 31, "city": "New York", "married": True}

    def test_apply_update(self, state: JsonDict, update: JsonDict, updated_state: JsonDict):
        assert JsonPatchUpdater.apply_update(state, update) == updated_state
