from fsspec.implementations.dirfs import DirFileSystem as FileSystem
import pytest

from rustic_ai.core.agents.commons.media import MediaLink
from rustic_ai.core.guild.agent_ext.depends.filesystem import FileSystemResolver
from rustic_ai.core.knowledgebase.agent_config import KnowledgeAgentConfig
from rustic_ai.core.knowledgebase.kbindex_backend_memory import InMemoryKBIndexBackend
from rustic_ai.core.knowledgebase.knowledge_base import KnowledgeBase
from rustic_ai.core.knowledgebase.pipeline_executor import SimplePipelineExecutor


@pytest.fixture
def filesystem(tmp_path) -> FileSystem:
    fsr = FileSystemResolver(
        path_base=str(tmp_path),
        protocol="file",
        storage_options={},
        asynchronous=True,
    )
    return fsr.resolve("test_guild", "test_agent")


@pytest.mark.asyncio
async def test_catalog_and_ingest_media(filesystem: FileSystem):
    cfg = KnowledgeAgentConfig.default_text(id="kb-test")
    kb = KnowledgeBase(
        config=cfg.to_kb_config(),
        filesystem=filesystem,
        library_path="library",
        executor=SimplePipelineExecutor(),
        index_backend=InMemoryKBIndexBackend(),
    )
    await kb.ensure_ready()

    # Prepare fake media bytes file in filesystem
    # Since DirFileSystem is rooted, create a file under library path is not required for catalog
    # We'll simulate a file path and rely on tests' filesystem fixture to resolve it.
    path = "sample.txt"
    await filesystem._pipe_file(path, b"Hello KB!\nThis is a second line.")
    media = [MediaLink(id="m1", url=f"file:///{path}", name="sample.txt", mimetype="text/plain")]

    statuses = await kb.ingest_media(media)
    assert len(statuses) == 1
    st = statuses[0]
    assert getattr(st, "status", None) in {"stored", "indexed", "indexing"} or getattr(st, "knol", None) is not None


@pytest.mark.asyncio
async def test_build_targets_and_search_text(filesystem: FileSystem):
    cfg = KnowledgeAgentConfig.default_text(id="kb-test-2")
    kb = KnowledgeBase(
        config=cfg.to_kb_config(),
        filesystem=filesystem,
        library_path="library",
        executor=SimplePipelineExecutor(),
        index_backend=InMemoryKBIndexBackend(),
    )
    await kb.ensure_ready()

    # Create media and ingest
    path = "doc.txt"
    await filesystem._pipe_file(path, b"first chunk text. second chunk text.")
    media = [MediaLink(id="m2", url=f"file:///{path}", name="doc.txt", mimetype="text/plain")]
    await kb.ingest_media(media)

    # Build search targets via helper
    targets = await kb.build_search_targets_from_text(text="first")
    assert len(targets) >= 1

    # Search via wrapper
    res = await kb.search_text(text="first", limit=5)
    assert res.search_duration_ms is not None
    assert isinstance(res.results, list)
