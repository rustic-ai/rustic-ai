from fsspec.implementations.dirfs import DirFileSystem as FileSystem
import pytest

from rustic_ai.core.guild.agent_ext.depends.filesystem.filesystem import (
    FileSystemResolver,
)
from rustic_ai.core.knowledgebase.chunks import TextChunk
from rustic_ai.core.knowledgebase.config import KBConfig, PluginRegistry
from rustic_ai.core.knowledgebase.kbindex_backend_memory import InMemoryKBIndexBackend
from rustic_ai.core.knowledgebase.knowledge_base import KnowledgeBase
from rustic_ai.core.knowledgebase.metadata import CommonMetaPart
from rustic_ai.core.knowledgebase.model import Knol
from rustic_ai.core.knowledgebase.pipeline import (
    ChunkerRef,
    EmbedderRef,
    PipelineSpec,
    SchemaRef,
    StorageSpec,
    TargetSelector,
)
from rustic_ai.core.knowledgebase.pipeline_executor import SimplePipelineExecutor
from rustic_ai.core.knowledgebase.plugins import ChunkerPlugin, EmbedderPlugin
from rustic_ai.core.knowledgebase.schema import (
    ColumnSpec,
    KBSchema,
    RoutingRule,
    RoutingSpec,
    TableMatch,
    TableSpec,
    VectorIndexSpec,
    VectorSpec,
)

# ---- Test doubles ----


class StubTextChunker(ChunkerPlugin):
    async def split(self, knol: Knol, *, fs: FileSystem, library_path: str = "library"):  # type: ignore[override]
        yield TextChunk(
            id=f"{knol.id}:{self.id}:0",
            knol_id=knol.id,
            index=0,
            producer_id=self.id,
            encoding="utf-8",
            content_bytes=b"first",
            language=knol.language,
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
            language=knol.language,
            mimetype="text/plain",
            name=knol.name,
        )


class StubTextEmbedder(EmbedderPlugin):
    dimension: int = 2

    async def embed(self, chunk, *, fs: FileSystem, library_path: str = "library"):  # type: ignore[override]
        return [1.0, 0.0]

    def supports_mimetype(self, mimetype: str) -> bool:  # type: ignore[override]
        return (mimetype or "").startswith("text/")


# ---- Helpers ----


def _schema_text() -> KBSchema:
    return KBSchema(
        id="kb-test",
        version=1,
        routing=RoutingSpec(
            rules=[RoutingRule(match=TableMatch(modality="text", mimetype="text/*"), table="text_chunks")]
        ),
        tables=[
            TableSpec(
                name="text_chunks",
                match=TableMatch(modality="text"),
                primary_key=["knol_id", "chunk_index"],
                columns=[
                    ColumnSpec(name="knol_id", type="string", source="knol", selector="id", nullable=False),
                    ColumnSpec(name="chunk_index", type="int", source="chunk", selector="index", nullable=False),
                    ColumnSpec(name="language", type="string", source="chunk", selector="language", nullable=True),
                    ColumnSpec(name="author", type="string", source="meta", selector="author", nullable=True),
                    ColumnSpec(name="text", type="text", source="chunk", selector="text", nullable=True),
                ],
                vector_columns=[
                    VectorSpec(name="vs_a", dim=2, distance="cosine", index=VectorIndexSpec(type="hnsw", params={})),
                ],
                indexes=[],
            )
        ],
    )


@pytest.fixture
def filesystem(tmp_path) -> FileSystem:
    fsr = FileSystemResolver(
        path_base=str(tmp_path),
        protocol="file",
        storage_options={},
        asynchronous=True,
    )
    return fsr.resolve("test_guild", "test_agent")


def _kb_config(schema: KBSchema) -> KBConfig:
    # Provide plugin instances in registry
    return KBConfig(
        id="kb",
        schema=schema,
        plugins=PluginRegistry(
            chunkers={"chunkerA": StubTextChunker(id="chunkerA")},
            projectors={},
            embedders={"embA": StubTextEmbedder(id="embA")},
        ),
        pipelines=[
            PipelineSpec(
                id="p1",
                schema_ref=SchemaRef(schema_id=schema.id, schema_version=schema.version),
                target=TargetSelector(modality="text", mimetype="text/plain"),
                chunker=ChunkerRef(chunker_id="chunkerA", policy_version="v1"),
                embedder=EmbedderRef(embedder_id="embA", embedder_version="v1"),
                storage=StorageSpec(vector_column="vs_a"),
            )
        ],
    )


def _knol() -> Knol:
    return Knol(id="k1", name="k1.txt", mimetype="text/plain", language="en", metaparts=[CommonMetaPart(author="ann")])


@pytest.mark.asyncio
async def test_kb_resolve_pipelines_and_ingest(filesystem: FileSystem):
    schema = _schema_text()
    cfg = _kb_config(schema)
    executor = SimplePipelineExecutor()
    backend = InMemoryKBIndexBackend()
    kb = KnowledgeBase(
        config=cfg, filesystem=filesystem, library_path="library", executor=executor, index_backend=backend
    )

    await kb.ensure_ready()

    # Resolve pipelines (pipeline_id -> vector_space_id)
    resolved = kb.resolve_pipelines([("p1", "vs_a")])
    assert len(resolved) == 1
    rp = resolved[0]
    assert rp.chunker_id == "chunkerA" and rp.vector_space_id == "vs_a"

    # Ingest a knol and verify two rows (two chunks) persisted
    await kb.ingest_knol(knol=_knol(), table_name="text_chunks", pipelines=resolved)

    results = await kb.search(table_name="text_chunks", vector_column="vs_a", query_vector=[1.0, 0.0], limit=10)
    assert len(results) == 2
    # Ensure scalar mapping exists
    langs = {r.payload.get("language") for r in results}
    assert langs == {"en"}
    authors = {r.payload.get("author") for r in results}
    assert authors == {"ann"}
