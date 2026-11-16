import pytest

from rustic_ai.core.utils.json_utils import JsonDict, JsonUtils


def test_create_missing_indexed_path_preserves_original_state():
    state: JsonDict = {}
    updated = JsonUtils.update_at_path(state, "$.users[0].name", "Alice")
    assert updated == {"users": [{"name": "Alice"}]}
    assert state == {}


def test_missing_multi_index_path_is_rejected():
    with pytest.raises(ValueError, match="multi-index JSONPath"):
        JsonUtils.update_at_path({}, "$.users[0,1].name", "Alice")
