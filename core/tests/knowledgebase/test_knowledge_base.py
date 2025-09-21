from typing import List

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
from rustic_ai.core.knowledgebase.rerankers.bm25_lite import BM25LiteReranker
from rustic_ai.core.knowledgebase.rerankers.diversity_mmr import MMRDiversityReranker
from rustic_ai.core.knowledgebase.rerankers.no_op import NoOpReranker
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
    chunks_to_produce: List[str]

    def __init__(self, id: str, chunks_to_produce: List[str]):
        super().__init__(id=id, chunks_to_produce=chunks_to_produce)

    async def split(self, knol: Knol, *, fs: FileSystem, library_path: str = "library"):  # type: ignore[override]
        for i, text in enumerate(self.chunks_to_produce):
            yield TextChunk(
                id=f"{knol.id}:{self.id}:{i}",
                knol_id=knol.id,
                index=i,
                producer_id=self.id,
                encoding="utf-8",
                content_bytes=text.encode("utf-8"),
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
            chunkers={"chunkerA": StubTextChunker(id="chunkerA", chunks_to_produce=["first", "second"])},
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
    cfg.plugins.rerankers["bm25"] = BM25LiteReranker(id="bm25")
    cfg.plugins.rerankers["mmr"] = MMRDiversityReranker(id="mmr")
    cfg.plugins.rerankers["noop"] = NoOpReranker(id="noop")
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


@pytest.mark.asyncio
async def test_search_with_noop_reranker(filesystem: FileSystem):
    schema = _schema_text()
    cfg = _kb_config_with_reranker(schema)
    # Configure a different chunker for this test
    cfg.plugins.chunkers["chunkerA"] = StubTextChunker(id="chunkerA", chunks_to_produce=["doc one", "doc two"])
    executor = SimplePipelineExecutor()
    backend = InMemoryKBIndexBackend()
    kb = KnowledgeBase(
        config=cfg, filesystem=filesystem, library_path="library", executor=executor, index_backend=backend
    )
    await kb.ensure_ready()
    resolved = kb.resolve_pipelines([("p1", "vs_a")])
    await kb.ingest_knol(knol=_knol(), table_name="text_chunks", pipelines=resolved)

    query = SearchQuery(
        vector=[1.0, 0.0],
        targets=[SearchTarget(table_name="text_chunks", vector_column="vs_a")],
        rerank=RerankOptions(strategy=RerankStrategy.RRF, model="noop"),
    )
    results = await kb.search(query=query)

    assert len(results) == 2
    assert results[0].chunk_id.endswith(":0")
    # Scores should be original vector scores, not transformed
    assert results[0].score > 0.99
    assert results[1].score < 0.01


@pytest.mark.asyncio
async def test_search_with_bm25_reranker(filesystem: FileSystem):
    schema = _schema_text()
    cfg = _kb_config_with_reranker(schema)
    # BM25 needs relevant text
    docs = ["the quick brown fox", "a slow lazy dog"]
    cfg.plugins.chunkers["chunkerA"] = StubTextChunker(id="chunkerA", chunks_to_produce=docs)

    executor = SimplePipelineExecutor()
    backend = InMemoryKBIndexBackend()
    kb = KnowledgeBase(
        config=cfg, filesystem=filesystem, library_path="library", executor=executor, index_backend=backend
    )
    await kb.ensure_ready()
    resolved = kb.resolve_pipelines([("p1", "vs_a")])
    await kb.ingest_knol(knol=_knol(), table_name="text_chunks", pipelines=resolved)

    # Vector search prefers doc 0 ([1,0]), but query text matches doc 1
    query = SearchQuery(
        text="lazy dog",
        vector=[1.0, 0.0],
        targets=[SearchTarget(table_name="text_chunks", vector_column="vs_a")],
        rerank=RerankOptions(strategy=RerankStrategy.RRF, model="bm25"),
    )
    results = await kb.search(query=query)

    assert len(results) == 2
    # BM25 should pull "a slow lazy dog" to the top
    assert results[0].chunk_id.endswith(":1")


@pytest.mark.asyncio
async def test_search_with_mmr_reranker(filesystem: FileSystem):
    schema = _schema_text()
    cfg = _kb_config_with_reranker(schema)
    docs = [
        "dogs are great companions",  # High relevance, similar to doc 1
        "dogs make wonderful pets",  # High relevance, similar to doc 0
        "cats are also nice",  # Low relevance, but diverse
    ]
    cfg.plugins.chunkers["chunkerA"] = StubTextChunker(id="chunkerA", chunks_to_produce=docs)
    cfg.plugins.embedders["embA"] = StubTextEmbedder(id="embA")  # Use default embedder behavior

    executor = SimplePipelineExecutor()
    backend = InMemoryKBIndexBackend()
    kb = KnowledgeBase(
        config=cfg, filesystem=filesystem, library_path="library", executor=executor, index_backend=backend
    )
    await kb.ensure_ready()
    resolved = kb.resolve_pipelines([("p1", "vs_a")])
    await kb.ingest_knol(knol=_knol(), table_name="text_chunks", pipelines=resolved)

    # Query is about dogs. Without MMR, the two dog documents should be first.
    # The embedder will make docs 0 and 2 have vector [1,0] and doc 1 have vector [0,1].
    # So a vector query for [1,0] will rank doc 0 and 2 highly.
    query = SearchQuery(
        text="dogs",
        vector=[1.0, 0.0],
        targets=[SearchTarget(table_name="text_chunks", vector_column="vs_a")],
        rerank=RerankOptions(strategy=RerankStrategy.RRF, model="mmr", top_n=3),
    )
    results = await kb.search(query=query)

    assert len(results) == 3
    # With MMR, after the first highly relevant "dog" document is selected (doc 0),
    # the next one should be the diverse "cats" document (doc 2), because
    # the other "dog" document (doc 1) is too similar to the first one.
    # However, our stub embedder makes doc 0 and 2 have the same embedding. Let's adjust.
    # The TF-IDF similarity in MMR will find doc 0 and 1 very similar.
    # Initial relevance (score) will be high for doc 0 and 2.
    # 1. Select doc 0 (highest score).
    # 2. For next pick, compare doc 1 and 2.
    #    - Doc 1: high relevance, but high similarity to doc 0. MMR score will be lower.
    #    - Doc 2: high relevance, low similarity to doc 0. MMR score will be higher.
    # So, the order should be [doc 0, doc 2, doc 1]
    result_ids = [r.chunk_id.split(":")[-1] for r in results]
    assert result_ids == ["0", "2", "1"]


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
            chunkers={"chunkerA": StubTextChunker(id="chunkerA", chunks_to_produce=["first", "second"])},
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
