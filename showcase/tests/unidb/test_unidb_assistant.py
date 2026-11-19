"""Showcase declaration and routing checks; native tool loop lives in unidb/tests."""

import json
from pathlib import Path

from jsonata import Jsonata
import pytest

APP = Path(__file__).resolve().parents[2] / "apps/unidb_assistant.json"


@pytest.fixture
def spec():
    return json.loads(APP.read_text())["spec"]


@pytest.mark.parametrize(
    "operation",
    [
        "CreateLabel",
        "CreateEdgeType",
        "AddProperty",
        "CreateScalarIndex",
        "CreateVectorIndex",
        "ListLabels",
        "ListEdgeTypes",
        "GetLabelInfo",
        "GetSchema",
        "Query",
        "Execute",
        "Flush",
        "VectorSearch",
        "InsertVertices",
        "InsertEdges",
    ],
)
def test_every_retained_operation_has_a_typed_round_trip(spec, operation):
    steps = spec["routes"]["steps"]
    assert any(
        s.get("message_format") == "rustic_ai.unidb.tools." + operation + "Arguments"
        and s["destination"]["topics"] == "unidb.tool.requests"
        for s in steps
    )
    assert any(
        s.get("message_format") == "rustic_ai.unidb.models." + operation + "Request"
        and s["destination"]["topics"] == "unidb"
        for s in steps
    )
    assert any(
        s.get("message_format") == "rustic_ai.unidb.models." + operation + "Response"
        and s["destination"]["topics"] == "unidb.observations"
        for s in steps
    )
    assert all(s.get("route_times") == -1 for s in steps)


def test_tool_declarations_and_explicit_binding(spec):
    assert len(spec["agents"]) == 3
    query, database, adapter = spec["agents"]
    wrapper = query["properties"]["llm_request_wrappers"][0]
    assert wrapper["kind"] == "rustic_ai.unidb.tools.UniDBToolsManagerPlugin"
    assert len(wrapper["toolset"]["tools"]) == 15
    assert database["properties"]["raw_operations_enabled"]
    assert database["dependency_map"]["unidb"]["properties"]["open_mode"] == "create"
    assert adapter["class_name"] == "rustic_ai.unidb.tools.UniDBToolAdapter"
    assert all(agent["listen_to_default_topic"] is False for agent in spec["agents"])


def test_error_recovery_is_guild_owned_and_validation_is_bounded(spec):
    steps = spec["routes"]["steps"]
    error = next(s for s in steps if s.get("message_format") == "rustic_ai.unidb.models.DBFailure")
    assert error["destination"]["topics"] == "unidb.observations"
    assert "process_status" not in error
    validation = next(s for s in steps if s.get("message_format", "").endswith(".ChatCompletionError"))
    assert validation["destination"]["topics"] == "user_message_broadcast"
    assert validation["process_status"] == "error"
    transformed = Jsonata(validation["transformer"]["handler"]).evaluate(
        {"payload": {"message": "Invalid tool parameters"}}
    )
    assert transformed["payload"]["text"] == "Invalid tool parameters"
