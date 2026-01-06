from fsspec.implementations.dirfs import DirFileSystem as FileSystem
import pytest

from rustic_ai.core.guild.agent_ext.depends.filesystem.filesystem import (
    FileSystemResolver,
)
from rustic_ai.core.knowledgebase.chunks import TextChunk
from rustic_ai.core.knowledgebase.model import Knol, Modality
from rustic_ai.core.knowledgebase.pipeline_executor import (
    EmittedRow,
    ResolvedPipeline,
    SimplePipelineExecutor,
)
from rustic_ai.core.knowledgebase.plugins import (
    ChunkerPlugin,
    EmbedderPlugin,
    ProjectorPlugin,
)

# ---------- Test doubles (plugins) ----------


class StubTextChunker(ChunkerPlugin):
    async def split(self, knol: Knol, *, fs: FileSystem, library_path: str = "library"):  # type: ignore[override]
        # Emit two tiny text chunks with indices 0 and 1
        yield TextChunk(
            id=f"{knol.id}:{self.id}:0",
            knol_id=knol.id,
            index=0,
            producer_id=self.id,
            encoding="utf-8",
            content_bytes=b"first",
            language="en",
            mimetype="text/plain",
            name=knol.name,
        )
        yield TextChunk(
            id=f"{knol.id}:{self.id}:1",
            knol_id=knol.id,
            index=1,
            producer_id=self.id,
            encoding="utf-8",
            content_bytes=b"second",
            language="en",
            mimetype="text/plain",
            name=knol.name,
        )


class StubTextProjector(ProjectorPlugin):
    source_modality: Modality = Modality.TEXT
    target_modality: Modality = Modality.TEXT
    target_mimetype: str | None = "text/plain"

    def supports_mimetype(self, mimetype: str) -> bool:  # type: ignore[override]
        return (mimetype or "").startswith("text/")

    async def project(self, chunk, *, fs: FileSystem, library_path: str = "library"):  # type: ignore[override]
        # Pass-through in tests, could normalize text here if needed
        return chunk


class StubTextEmbedder(EmbedderPlugin):
    dimension: int = 2

    def __init__(self, **data):
        super().__init__(**data)
        self._vec = [1.0, 0.0]

    def supports_mimetype(self, mimetype: str) -> bool:  # type: ignore[override]
        return (mimetype or "").startswith("text/")

    async def embed(self, chunk, *, fs: FileSystem, library_path: str = "library"):  # type: ignore[override]
        return list(self._vec)


class StubRejectingEmbedder(EmbedderPlugin):
    dimension: int = 1

    def supports_mimetype(self, mimetype: str) -> bool:  # type: ignore[override]
        return False

    async def embed(self, chunk, *, fs: FileSystem, library_path: str = "library"):  # type: ignore[override]
        return [0.0]


# ---------- Fixtures ----------


@pytest.fixture
def filesystem(tmp_path) -> FileSystem:
    fsr = FileSystemResolver(
        path_base=str(tmp_path),
        protocol="file",
        storage_options={},
        asynchronous=True,
    )
    return fsr.resolve("test_org", "test_guild", "test_agent")


def _make_knol() -> Knol:
    return Knol(id="knol1", name="doc1", mimetype="text/plain", language="en")


# ---------- Tests ----------


@pytest.mark.asyncio
async def test_executor_aggregates_multiple_vector_spaces(filesystem: FileSystem):
    knol = _make_knol()
    chunker = StubTextChunker(id="chunkerA")

    emb1 = StubTextEmbedder(id="emb1")
    emb1._vec = [1.0, 0.0]
    emb2 = StubTextEmbedder(id="emb2")
    emb2._vec = [0.0, 2.0]

    rp1 = ResolvedPipeline(
        id="p1",
        chunker_id="chunkerA",
        policy_version="v1",
        vector_space_id="vs_a",
        chunker=chunker,
        embedder=emb1,
        projector=None,
    )
    rp2 = ResolvedPipeline(
        id="p2",
        chunker_id="chunkerA",
        policy_version="v1",
        vector_space_id="vs_b",
        chunker=chunker,
        embedder=emb2,
        projector=None,
    )

    ex = SimplePipelineExecutor()
    rows = [
        row async for row in ex.rows_for_knol(knol=knol, fs=filesystem, library_path="library", pipelines=[rp1, rp2])
    ]

    # Expect one row per chunk index (2 chunks), each containing both vector spaces
    assert len(rows) == 2
    for r in rows:
        assert isinstance(r, EmittedRow)
        assert r.knol.id == knol.id
        assert set(r.vectors.keys()) == {"vs_a", "vs_b"}


@pytest.mark.asyncio
async def test_executor_projector_and_unsupported_embedder(filesystem: FileSystem):
    knol = _make_knol()
    chunker = StubTextChunker(id="chunkerB")
    projector = StubTextProjector(id="proj1")

    emb_ok = StubTextEmbedder(id="emb_ok")
    emb_ok._vec = [3.0, 4.0]
    emb_skip = StubRejectingEmbedder(id="emb_no")

    rp_ok = ResolvedPipeline(
        id="p_ok",
        chunker_id="chunkerB",
        policy_version="v1",
        vector_space_id="vs_ok",
        chunker=chunker,
        embedder=emb_ok,
        projector=projector,
    )
    rp_no = ResolvedPipeline(
        id="p_no",
        chunker_id="chunkerB",
        policy_version="v1",
        vector_space_id="vs_no",
        chunker=chunker,
        embedder=emb_skip,
        projector=projector,
    )

    ex = SimplePipelineExecutor()
    rows = [
        row
        async for row in ex.rows_for_knol(knol=knol, fs=filesystem, library_path="library", pipelines=[rp_ok, rp_no])
    ]

    # Each chunk should have only the supported vector space
    assert len(rows) == 2
    for r in rows:
        assert set(r.vectors.keys()) == {"vs_ok"}
        assert r.vectors["vs_ok"] == [3.0, 4.0]


@pytest.mark.asyncio
async def test_executor_groups_by_policy(filesystem: FileSystem):
    knol = _make_knol()
    chunker1 = StubTextChunker(id="chunkerC")
    chunker2 = StubTextChunker(id="chunkerD")
    emb = StubTextEmbedder(id="embX")

    rp_c = ResolvedPipeline(
        id="p_c",
        chunker_id="chunkerC",
        policy_version="v1",
        vector_space_id="vs_c",
        chunker=chunker1,
        embedder=emb,
        projector=None,
    )
    rp_d = ResolvedPipeline(
        id="p_d",
        chunker_id="chunkerD",
        policy_version="v1",
        vector_space_id="vs_d",
        chunker=chunker2,
        embedder=emb,
        projector=None,
    )

    ex = SimplePipelineExecutor()
    rows = [
        row async for row in ex.rows_for_knol(knol=knol, fs=filesystem, library_path="library", pipelines=[rp_c, rp_d])
    ]

    # Two chunkers -> 2 groups -> per chunk index, two separate rows
    # Stub emits 2 chunks -> expect 4 rows total
    assert len(rows) == 4
    # Ensure vector spaces do not mix across groups
    for r in rows:
        assert set(r.vectors.keys()) in ({"vs_c"}, {"vs_d"})
