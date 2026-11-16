import json
from pathlib import Path
from types import SimpleNamespace

from fsspec import filesystem
from fsspec.implementations.asyn_wrapper import AsyncFileSystemWrapper
from fsspec.implementations.dirfs import DirFileSystem
import pandas as pd
import pytest

from rustic_ai.core.guild.agent_ext.depends.code_execution.data_analyzer import (
    InvalidQueryError,
    QueryExecutionRequest,
)
from rustic_ai.core.guild.agent_ext.depends.filesystem import FileSystemResolver
from rustic_ai.core.guild.metaprog.agent_registry import AgentRegistry
from rustic_ai.llm_agent.react import ToolOutcomeDisposition
from rustic_ai.pandas_analyst import PandasDataAnalyzer
from rustic_ai.pandas_analyst.file_url_preprocessor import FileUrlExtractorPreprocessor
from rustic_ai.pandas_analyst.react_toolset import (
    DataAnalystReActToolset,
    LoadFileRequest,
)


def bound_toolset(root: Path) -> DataAnalystReActToolset:
    toolset = DataAnalystReActToolset()
    toolset.bind_filesystem(DirFileSystem(path=str(root), fs=filesystem("file")))
    return toolset


def test_studio_async_filesystem_profile_is_bound_for_sync_analysis(tmp_path: Path) -> None:
    (tmp_path / "sales.csv").write_text("region,revenue\nWest,10\n", encoding="utf-8")
    resolved = FileSystemResolver(
        path_base=str(tmp_path.parent),
        protocol="file",
        storage_options={"auto_mkdir": True},
        asynchronous=True,
    ).resolve(".", tmp_path.name, ".")
    toolset = DataAnalystReActToolset()

    toolset.bind_filesystem(resolved)
    result = toolset.execute("load_file", LoadFileRequest(filename="sales.csv", dataset_name="sales"))

    assert toolset.interpret_result("load_file", LoadFileRequest(filename="sales.csv"), result).disposition == (
        ToolOutcomeDisposition.SUCCESS
    )
    assert toolset.analyzer.list_datasets().datasets == ["sales"]
    assert resolved.asynchronous is True
    assert isinstance(resolved.fs, AsyncFileSystemWrapper)
    assert toolset.filesystem is not resolved
    assert toolset.filesystem.asynchronous is False


def test_agent_declares_llm_and_guild_filesystem_dependencies():
    entry = AgentRegistry.get_agent("rustic_ai.pandas_analyst.agent.DataAnalystAgent")

    assert entry is not None
    dependencies = {item.dependency_key: item for item in entry.agent_dependencies}
    assert dependencies["llm"].required_type == "rustic_ai.core.guild.agent_ext.depends.llm.llm.LLM"
    assert dependencies["filesystem"].guild_level is True
    assert dependencies["filesystem"].agent_level is False
    assert dependencies["filesystem"].required_type == "fsspec.implementations.dirfs.DirFileSystem"


@pytest.mark.parametrize(
    "filename",
    [
        "",
        "   ",
        "/etc/passwd",
        "../sibling/private.csv",
        "nested/../../private.csv",
        "%2e%2e/private.csv",
        "%252e%252e/private.csv",
        "C:\\private.csv",
        "\\\\server\\share\\private.csv",
        "file:///etc/passwd",
        "https://example.invalid/data.csv",
        "bad\x00name.csv",
    ],
)
def test_unsafe_file_paths_fail_terminally(tmp_path: Path, filename: str):
    toolset = bound_toolset(tmp_path)

    result = toolset.execute("load_file", LoadFileRequest(filename=filename))
    outcome = toolset.interpret_result("load_file", LoadFileRequest(filename=filename), result)

    assert outcome.disposition == ToolOutcomeDisposition.TERMINAL_ERROR
    assert outcome.code == "unsafe_file_path"
    assert str(tmp_path) not in result


def test_safe_nested_guild_file_loads_but_sibling_file_does_not(tmp_path: Path):
    guild_root = tmp_path / "guild" / "GUILD_GLOBAL"
    nested = guild_root / "nested"
    nested.mkdir(parents=True)
    (nested / "sales.csv").write_text("id,total\n1,10\n2,20\n")
    sibling = tmp_path / "other-guild" / "GUILD_GLOBAL"
    sibling.mkdir(parents=True)
    (sibling / "private.csv").write_text("secret\nprivate\n")
    toolset = bound_toolset(guild_root)

    loaded = toolset.execute(
        "load_file",
        LoadFileRequest(filename="nested/sales.csv", dataset_name="sales"),
    )
    escaped = toolset.execute(
        "load_file",
        LoadFileRequest(filename="../../other-guild/GUILD_GLOBAL/private.csv"),
    )

    assert json.loads(loaded)["name"] == "sales"
    assert toolset.interpret_result("load_file", LoadFileRequest(filename="x"), escaped).disposition == (
        ToolOutcomeDisposition.TERMINAL_ERROR
    )
    assert "private" not in escaped


@pytest.mark.parametrize("file_format", ["csv", "json", "parquet"])
def test_supported_guild_file_formats_load(tmp_path: Path, file_format: str):
    frame = pd.DataFrame({"id": [1, 2], "total": [10, 20]})
    filename = f"sales.{file_format}"
    path = tmp_path / filename
    if file_format == "csv":
        frame.to_csv(path, index=False)
    elif file_format == "json":
        frame.to_json(path, orient="records")
    else:
        frame.to_parquet(path, index=False)
    toolset = bound_toolset(tmp_path)

    result = toolset.execute("load_file", LoadFileRequest(filename=filename, dataset_name="sales"))
    outcome = toolset.interpret_result("load_file", LoadFileRequest(filename=filename), result)

    assert outcome.disposition == ToolOutcomeDisposition.SUCCESS
    assert json.loads(result)["name"] == "sales"


def test_expected_tool_errors_and_clarification_have_explicit_outcomes(tmp_path: Path):
    toolset = bound_toolset(tmp_path)

    missing = toolset.execute("load_file", LoadFileRequest(filename="missing.csv"))
    missing_outcome = toolset.interpret_result("load_file", LoadFileRequest(filename="missing.csv"), missing)
    clarification = toolset.execute("ask_user", {"question": " Which column should I group by? "})
    clarification_outcome = toolset.interpret_result("ask_user", LoadFileRequest(filename="unused"), clarification)

    assert missing_outcome.disposition == ToolOutcomeDisposition.RETRYABLE_ERROR
    assert missing_outcome.code == "file_load_failed"
    assert clarification_outcome.disposition == ToolOutcomeDisposition.CLARIFICATION_REQUIRED
    assert clarification_outcome.message == "Which column should I group by?"


def test_guild_file_context_is_bounded_and_contains_no_physical_root(tmp_path: Path):
    for index in range(60):
        (tmp_path / f"file-{index:02}.csv").write_text("value\n1\n")
    (tmp_path / ".file-00.csv.meta").write_text("internal")
    hidden_directory = tmp_path / ".internal"
    hidden_directory.mkdir()
    (hidden_directory / "upload.json").write_text("{}")
    toolset = bound_toolset(tmp_path)
    agent = SimpleNamespace(config=SimpleNamespace(toolset=toolset))

    names = FileUrlExtractorPreprocessor()._get_guild_files(agent)

    assert len(names) == 50
    assert names == sorted(names)
    assert all(str(tmp_path) not in name for name in names)
    assert all(not any(part.startswith(".") for part in Path(name).parts) for name in names)


@pytest.mark.parametrize(
    "query",
    [
        "SELECT * FROM read_csv_auto('/etc/passwd')",
        "ATTACH '/tmp/rustic-data-analyst-test.duckdb' AS external_db",
        "COPY (SELECT 1) TO '/tmp/rustic-data-analyst-test.csv'",
        "INSTALL httpfs",
        "LOAD httpfs",
        "SET enable_external_access=true",
        "SELECT * FROM 'https://example.invalid/private.csv'",
    ],
)
def test_duckdb_external_access_is_disabled(query: str):
    with pytest.raises(InvalidQueryError):
        PandasDataAnalyzer().execute_query(
            QueryExecutionRequest(query_language="sql", query_string=query, input_datasets={})
        )


def test_unexpected_analyzer_failure_is_terminal_and_sanitized(tmp_path: Path):
    class BrokenAnalyzer:
        datasets: dict[str, object] = {}

        def execute_query(self, request):
            del request
            raise RuntimeError("PRIVATE_HOST_PATH=/private/neighbor-guild")

    toolset = bound_toolset(tmp_path)
    toolset._analyzer = BrokenAnalyzer()
    arguments = QueryExecutionRequest(
        query_language="sql",
        query_string="SELECT 1",
        input_datasets={},
    )

    result = toolset.execute("query_dataset", arguments)
    outcome = toolset.interpret_result("query_dataset", arguments, result)

    assert outcome.disposition == ToolOutcomeDisposition.TERMINAL_ERROR
    assert outcome.code == "unexpected_data_failure"
    assert "PRIVATE_HOST_PATH" not in result
    assert "neighbor-guild" not in result
