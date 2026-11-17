"""Uniko persistence uses the injected private filesystem, never cwd."""

import asyncio
import gc
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from uniko import Scope, Turn

from rustic_ai.core.agents.commons.media import MediaLink
from rustic_ai.core.guild.agent_ext.depends.dependency_resolver import DependencySpec
from rustic_ai.core.guild.metaprog import AgentAnnotations
from rustic_ai.core.guild.metaprog.agent_registry import AgentRegistry
from rustic_ai.uniko_agent import IngestDocumentRequest, MemoryAgent
from rustic_ai.uniko_agent.resolver import UnikoResolver


def resolver_for(root, asynchronous=False, protocol="file"):
    resolver = UnikoResolver(storage_path="memory")
    resolver.set_dependency_specs(
        {
            "filesystem": DependencySpec(
                class_name="rustic_ai.core.guild.agent_ext.depends.filesystem.FileSystemResolver",
                properties={
                    "path_base": str(root),
                    "protocol": protocol,
                    "storage_options": {"auto_mkdir": True},
                    "asynchronous": asynchronous,
                },
            )
        }
    )
    return resolver


def test_memory_agent_declares_both_filesystem_scopes():
    entry = AgentRegistry.get_agent(MemoryAgent.get_qualified_class_name())
    declarations = MemoryAgent.ingest_document.__annotations__[AgentAnnotations.DEPENDS_ON]
    fs = [dep for dep in declarations if dep.dependency_key == "filesystem"]
    assert {dep.guild_level for dep in fs} == {False, True}
    assert all(dep.agent_level for dep in entry.agent_dependencies if dep.dependency_key == "uniko")


@pytest.mark.asyncio
async def test_guild_filesystem_failure_is_sanitized():
    request = IngestDocumentRequest(
        record_id="source-1",
        session_id="research",
        media_link=MediaLink(
            url="/scraped_data/source.md",
            on_filesystem=True,
        ),
    )
    ctx = SimpleNamespace(payload=request, send=MagicMock(), send_error=MagicMock())
    memory = SimpleNamespace(
        _session_lock=lambda *args: asyncio.Lock(),
        _producer_is_allowed=lambda *_: True,
        config=SimpleNamespace(max_source_bytes=16 * 1024 * 1024),
    )
    memory._send_failure = lambda ctx, code: MemoryAgent._send_failure(memory, ctx, code)
    guild_fs = SimpleNamespace(asynchronous=False, open=MagicMock(side_effect=OSError("PRIVATE_BACKEND_DETAILS")))
    private_fs = MagicMock()
    await MemoryAgent.ingest_document.__wfn__(
        memory,
        ctx,
        SimpleNamespace(session=lambda _: None),
        private_fs,
        guild_fs,
    )
    ctx.send.assert_not_called()
    ctx.send_error.assert_called_once()
    error = ctx.send_error.call_args.args[0]
    assert error.error == "document_ingest_failed"
    assert "PRIVATE_BACKEND_DETAILS" not in error.model_dump_json()
    assert private_fs.mock_calls == []


@pytest.mark.parametrize("asynchronous", [False, True])
def test_storage_scope_cache_and_cwd_independence(tmp_path, monkeypatch, asynchronous):
    root = tmp_path / "workspaces"
    resolver = resolver_for(root, asynchronous)
    builder = MagicMock()
    builder.path.return_value = builder
    builder.build_sync.side_effect = lambda: MagicMock()
    with patch("rustic_ai.uniko_agent.resolver.uniko.Uniko.builder", return_value=builder):
        first = resolver.get_or_resolve("org", "guild", "memory-agent")
        monkeypatch.chdir(tmp_path)
        assert resolver.get_or_resolve("org", "guild", "memory-agent") is first
        resolver.get_or_resolve("org", "guild", "other-agent")
        resolver.get_or_resolve("org", "other-guild", "memory-agent")
        resolver.get_or_resolve("other-org", "guild", "memory-agent")
    assert [call.args[0] for call in builder.path.call_args_list] == [
        str(root / "org/guild/memory-agent/memory"),
        str(root / "org/guild/other-agent/memory"),
        str(root / "org/other-guild/memory-agent/memory"),
        str(root / "other-org/guild/memory-agent/memory"),
    ]
    resolver.shutdown()


def test_persistence_requires_filesystem_and_rejects_remote_backing(tmp_path):
    with pytest.raises(ValueError, match="not registered"):
        UnikoResolver(storage_path="memory").get_or_resolve("org", "guild", "agent")
    with pytest.raises(ValueError, match="local agent filesystem"):
        resolver_for(tmp_path, protocol="memory").get_or_resolve("org", "guild", "agent")


def test_private_memory_survives_resolver_restart(tmp_path, monkeypatch):
    root = tmp_path / "workspaces"
    first = resolver_for(root)
    handle = first.get_or_resolve("org", "guild", "memory-agent")
    session = handle.session("user-session")
    session.observe_sync(Turn("user", "My preferred database is PostgreSQL.").id("turn-1"))
    session.finalize_sync()
    del session, handle
    first.cache.clear()
    gc.collect()
    first.shutdown()

    monkeypatch.chdir(tmp_path)
    reopened = resolver_for(root)
    handle = reopened.get_or_resolve("org", "guild", "memory-agent")
    bundle = handle.recall_in_sync("preferred database", Scope().sessions(["user-session"]))
    assert bundle.items
    other = reopened.get_or_resolve("org", "guild", "other-agent")
    assert not other.recall_in_sync("preferred database", Scope().sessions(["user-session"])).items
    del bundle, handle, other
    reopened.cache.clear()
    gc.collect()
    reopened.shutdown()
