"""The source and installed catalog use one set of JSON envelopes."""

import json
from pathlib import Path

import pytest

from rustic_ai.showcase.catalog import list_blueprints, load_blueprint

EXPECTED = (
    "debate_simulator_blueprint.json",
    "iterative_studio/iterative_studio.json",
    "llm_council.json",
    "multi_llm_blueprint.json",
    "paper_banana_guild.json",
    "personal_workspace.json",
    "react_data_analyst.json",
    "researcher.json",
    "semantic_memory_assistant.json",
    "todo_guild.json",
    "ui_component_blueprint.json",
    "unidb_assistant.json",
    "unidb_query_diagnostics.json",
    "uniko_research_guild.json",
    "vending_bench_guild.json",
    "vending_bench_player_guild.json",
)


def test_catalog_resources_match_authoring_sources():
    assert list_blueprints() == EXPECTED
    source = Path(__file__).resolve().parents[1] / "apps"
    for name in EXPECTED:
        assert load_blueprint(name) == json.loads((source / name).read_text())


@pytest.mark.parametrize(
    "name", ["../pyproject.toml", "/etc/passwd", "iterative_studio/../todo_guild.json", "missing.json"]
)
def test_catalog_rejects_unknown_or_noncanonical_paths(name):
    with pytest.raises(FileNotFoundError):
        load_blueprint(name)
