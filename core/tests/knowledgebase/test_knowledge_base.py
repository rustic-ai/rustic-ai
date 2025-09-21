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
from rustic_ai.core.knowledgebase.query import (
    HybridOptions,
    RerankOptions,
    RerankStrategy,
    SearchQuery,
    SearchTarget,
)
from rustic_ai.core.knowledgebase.rerankers.rrf import RRFReranker
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
        # Distinguish embeddings per chunk index for testing dense scoring
        idx = getattr(chunk, "index", 0) or 0
        if idx % 2 == 0:
            return [1.0, 0.0]
        return [0.0, 1.0]

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


def _knol2() -> Knol:
    return Knol(id="k2", name="k2.txt", mimetype="text/plain", language="en", metaparts=[CommonMetaPart(author="bob")])


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

    results = await kb.search(
        query=SearchQuery(
            vector=[1.0, 0.0],
            targets=[SearchTarget(table_name="text_chunks", vector_column="vs_a")],
            limit=10,
        )
    )
    assert len(results) == 2
    # Ensure scalar mapping exists
    langs = {r.payload.get("language") for r in results}
    assert langs == {"en"}
    authors = {r.payload.get("author") for r in results}
    assert authors == {"ann"}


@pytest.mark.asyncio
async def test_hybrid_text_search_dense_and_sparse(filesystem: FileSystem):
    schema = _schema_text()
    cfg = _kb_config(schema)
    executor = SimplePipelineExecutor()
    backend = InMemoryKBIndexBackend()
    kb = KnowledgeBase(
        config=cfg, filesystem=filesystem, library_path="library", executor=executor, index_backend=backend
    )

    await kb.ensure_ready()
    resolved = kb.resolve_pipelines([("p1", "vs_a")])
    await kb.ingest_knol(knol=_knol(), table_name="text_chunks", pipelines=resolved)

    # Dense-only should prefer chunk index 0 (embedding [1,0])
    dense_only = await kb.search(
        query=SearchQuery(
            vector=[1.0, 0.0], targets=[SearchTarget(table_name="text_chunks", vector_column="vs_a")], limit=10
        )
    )
    assert len(dense_only) >= 1
    assert dense_only[0].chunk_id.endswith(":0")

    # Sparse-only with text "second" should prefer chunk index 1
    sparse_only = await kb.search(
        query=SearchQuery(
            text="second", targets=[SearchTarget(table_name="text_chunks", vector_column="vs_a")], limit=10
        )
    )
    assert len(sparse_only) >= 1
    assert sparse_only[0].chunk_id.endswith(":1")

    # Hybrid with heavier sparse weight should prefer chunk index 1
    hybrid = await kb.search(
        query=SearchQuery(
            text="second",
            vector=[1.0, 0.0],
            targets=[SearchTarget(table_name="text_chunks", vector_column="vs_a")],
            hybrid=HybridOptions(dense_weight=0.3, sparse_weight=0.7),
            limit=10,
        )
    )
    assert len(hybrid) >= 1
    assert hybrid[0].chunk_id.endswith(":1")


def _kb_config_with_reranker(schema: KBSchema) -> KBConfig:
    cfg = _kb_config(schema)
    cfg.plugins.rerankers["rrf"] = RRFReranker(id="rrf")
    return cfg


@pytest.mark.asyncio
async def test_search_with_reranker(filesystem: FileSystem):
    schema = _schema_text()
    cfg = _kb_config_with_reranker(schema)
    executor = SimplePipelineExecutor()
    backend = InMemoryKBIndexBackend()
    kb = KnowledgeBase(
        config=cfg, filesystem=filesystem, library_path="library", executor=executor, index_backend=backend
    )

    await kb.ensure_ready()
    resolved = kb.resolve_pipelines([("p1", "vs_a")])
    await kb.ingest_knol(knol=_knol(), table_name="text_chunks", pipelines=resolved)

    # Initial search (dense-only) prefers chunk 0
    query_no_rerank = SearchQuery(
        vector=[1.0, 0.0],
        targets=[SearchTarget(table_name="text_chunks", vector_column="vs_a")],
        limit=10,
    )
    results_no_rerank = await kb.search(query=query_no_rerank)
    assert len(results_no_rerank) == 2
    assert results_no_rerank[0].chunk_id.endswith(":0")
    original_score_0 = results_no_rerank[0].score
    original_score_1 = results_no_rerank[1].score
    assert original_score_0 > original_score_1

    # Search with RRF reranking. The scores should change according to RRF formula.
    query_with_rerank = SearchQuery(
        vector=[1.0, 0.0],
        targets=[SearchTarget(table_name="text_chunks", vector_column="vs_a")],
        limit=10,
        rerank=RerankOptions(strategy=RerankStrategy.RRF, model="rrf", top_n=10),
    )
    results_reranked = await kb.search(query=query_with_rerank)
    assert len(results_reranked) == 2
    assert results_reranked[0].chunk_id.endswith(":0")  # Order should be preserved as RRF is rank-based
    # Check that scores have been transformed
    assert results_reranked[0].score == 1.0 / (60 + 1)
    assert results_reranked[1].score == 1.0 / (60 + 2)


def _schema_text_multi() -> KBSchema:
    return KBSchema(
        id="kb-test-multi",
        version=1,
        routing=RoutingSpec(
            rules=[
                RoutingRule(match=TableMatch(modality="text", mimetype="text/*"), table="text_chunks"),
                RoutingRule(match=TableMatch(modality="text", mimetype="text/*"), table="notes_chunks"),
            ]
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
            ),
            TableSpec(
                name="notes_chunks",
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
            ),
        ],
    )


def _kb_config_multi(schema: KBSchema) -> KBConfig:
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
            ),
            PipelineSpec(
                id="p2",
                schema_ref=SchemaRef(schema_id=schema.id, schema_version=schema.version),
                target=TargetSelector(modality="text", mimetype="text/plain"),
                chunker=ChunkerRef(chunker_id="chunkerA", policy_version="v1"),
                embedder=EmbedderRef(embedder_id="embA", embedder_version="v1"),
                storage=StorageSpec(vector_column="vs_a"),
            ),
        ],
    )


@pytest.mark.asyncio
async def test_multitable_fanout_and_fusion(filesystem: FileSystem):
    schema = _schema_text_multi()
    cfg = _kb_config_multi(schema)
    executor = SimplePipelineExecutor()
    backend = InMemoryKBIndexBackend()
    kb = KnowledgeBase(
        config=cfg, filesystem=filesystem, library_path="library", executor=executor, index_backend=backend
    )

    await kb.ensure_ready()
    resolved = kb.resolve_pipelines([("p1", "vs_a"), ("p2", "vs_a")])

    # Ingest two different knols into two different tables
    await kb.ingest_knol(knol=_knol(), table_name="text_chunks", pipelines=[p for p in resolved if p.id == "p1"])
    await kb.ingest_knol(knol=_knol2(), table_name="notes_chunks", pipelines=[p for p in resolved if p.id == "p2"])

    # Heavier weight on text_chunks should prefer k1's chunk
    q1 = SearchQuery(
        vector=[1.0, 0.0],
        targets=[
            SearchTarget(table_name="text_chunks", vector_column="vs_a", weight=1.0),
            SearchTarget(table_name="notes_chunks", vector_column="vs_a", weight=0.3),
        ],
        limit=5,
    )
    r1 = await kb.search(query=q1)
    assert len(r1) >= 1
    assert r1[0].chunk_id.startswith("k1:")

    # Flip weights to prefer notes_chunks
    q2 = SearchQuery(
        vector=[1.0, 0.0],
        targets=[
            SearchTarget(table_name="text_chunks", vector_column="vs_a", weight=0.3),
            SearchTarget(table_name="notes_chunks", vector_column="vs_a", weight=1.0),
        ],
        limit=5,
    )
    r2 = await kb.search(query=q2)
    assert len(r2) >= 1
    assert r2[0].chunk_id.startswith("k2:")
