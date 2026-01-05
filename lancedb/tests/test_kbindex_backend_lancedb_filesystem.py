"""Integration tests for filesystem-aware LanceDB backend."""
from typing import AsyncIterable

import pytest
from fsspec import filesystem
from fsspec.implementations.dirfs import DirFileSystem

from rustic_ai.core.knowledgebase.chunks import TextChunk
from rustic_ai.core.knowledgebase.metadata import CommonMetaPart
from rustic_ai.core.knowledgebase.model import Knol
from rustic_ai.core.knowledgebase.pipeline_executor import EmittedRow
from rustic_ai.core.knowledgebase.query import (
    BoolFilter,
    FilterClause,
    FilterOp,
    SearchQuery,
    SearchTarget,
)
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
from rustic_ai.lancedb.kbindex_backend_lancedb import (
    LanceDBKBIndexBackend,
    LanceDBKBIndexBackendResolver,
)


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


def _row(knol_id: str, text: str, lang: str = "en") -> EmittedRow:
    knol = Knol(
        id=knol_id,
        name=f"{knol_id}.txt",
        mimetype="text/plain",
        language=lang,
        metaparts=[CommonMetaPart(author="alice")],
    )
    chunk = TextChunk(
        id=f"{knol_id}:chunkerA:0",
        knol_id=knol.id,
        index=0,
        producer_id="chunkerA",
        encoding="utf-8",
        content_bytes=text.encode("utf-8"),
        language=lang,
        mimetype="text/plain",
        name=knol.name,
    )
    return EmittedRow(chunk_id=chunk.id, knol=knol, chunk=chunk, vectors={"vs_a": [1.0, 0.0]})


async def _aiter_one(r: EmittedRow) -> AsyncIterable[EmittedRow]:
    yield r


class TestLanceDBFilesystemIntegration:
    """Integration tests for filesystem-aware LanceDB backend."""

    @pytest.mark.asyncio
    async def test_backend_with_local_filesystem(self, tmp_path):
        """Test LanceDB backend with local filesystem."""
        # Create a filesystem
        base_path = str(tmp_path / "lancedb_storage")
        fs = filesystem("file", auto_mkdir=True)
        dirfs = DirFileSystem(path=base_path, fs=fs)

        # Create backend without explicit URI (should auto-generate)
        schema = _schema_text()
        backend = LanceDBKBIndexBackend(uri=None, filesystem=dirfs)
        await backend.ensure_ready(schema=schema)

        # Verify URI was auto-generated
        assert backend._uri is not None
        assert backend._uri.startswith("file://")
        assert "kb-test" in backend._uri  # schema.id

        # Test basic operations
        row = _row("k1", "hello filesystem", "en")
        await backend.upsert(table_name="text_chunks", rows=_aiter_one(row))

        res = await backend.search(
            query=SearchQuery(
                targets=[SearchTarget(table_name="text_chunks", vector_column="vs_a", query_vector=[1.0, 0.0])],
                limit=10,
            )
        )
        assert len(res) == 1
        assert res[0].chunk_id == row.chunk_id
        assert res[0].payload.get("text") == "hello filesystem"

    @pytest.mark.asyncio
    async def test_backend_with_memory_filesystem(self):
        """Test LanceDB backend with in-memory filesystem."""
        # Create a memory filesystem
        fs = filesystem("memory")
        base_path = "/lancedb_test"
        fs.makedirs(base_path, exist_ok=True)
        dirfs = DirFileSystem(path=base_path, fs=fs)

        # Create backend without explicit URI
        schema = _schema_text()
        backend = LanceDBKBIndexBackend(uri=None, filesystem=dirfs)
        await backend.ensure_ready(schema=schema)

        # Verify URI was auto-generated with memory protocol
        assert backend._uri is not None
        assert backend._uri.startswith("memory://")
        assert "kb-test" in backend._uri

        # Test operations
        row1 = _row("mem1", "memory test 1", "en")
        row2 = _row("mem2", "memory test 2", "fr")
        
        async def _rows():
            yield row1
            yield row2

        await backend.upsert(table_name="text_chunks", rows=_rows())

        # Search for all
        res = await backend.search(
            query=SearchQuery(
                targets=[SearchTarget(table_name="text_chunks", vector_column="vs_a", query_vector=[1.0, 0.0])],
                limit=10,
            )
        )
        assert len(res) == 2

        # Filter by language
        res_en = await backend.search(
            query=SearchQuery(
                targets=[SearchTarget(table_name="text_chunks", vector_column="vs_a", query_vector=[1.0, 0.0])],
                limit=10,
                filter=BoolFilter(must=[FilterClause(field="language", op=FilterOp.EQ, value="en")]),
            )
        )
        assert len(res_en) == 1
        assert res_en[0].chunk_id == row1.chunk_id

    @pytest.mark.asyncio
    async def test_backend_with_explicit_uri_overrides_filesystem(self, tmp_path):
        """Test that explicit URI takes precedence over filesystem-based URI."""
        # Create a filesystem
        base_path = str(tmp_path / "unused_path")
        fs = filesystem("file", auto_mkdir=True)
        dirfs = DirFileSystem(path=base_path, fs=fs)

        # Provide explicit URI
        explicit_uri = str(tmp_path / "explicit_lancedb")
        schema = _schema_text()
        backend = LanceDBKBIndexBackend(uri=explicit_uri, filesystem=dirfs)
        await backend.ensure_ready(schema=schema)

        # Verify explicit URI is used
        assert backend._uri == explicit_uri

        # Test it works
        row = _row("k1", "explicit uri test", "en")
        await backend.upsert(table_name="text_chunks", rows=_aiter_one(row))

        res = await backend.search(
            query=SearchQuery(
                targets=[SearchTarget(table_name="text_chunks", vector_column="vs_a", query_vector=[1.0, 0.0])],
                limit=10,
            )
        )
        assert len(res) == 1

    @pytest.mark.asyncio
    async def test_backend_persistence_across_instances(self, tmp_path):
        """Test that data persists across backend instances with same filesystem."""
        # Create a filesystem
        base_path = str(tmp_path / "persistent_storage")
        fs = filesystem("file", auto_mkdir=True)
        dirfs = DirFileSystem(path=base_path, fs=fs)

        schema = _schema_text()

        # First instance: write data
        backend1 = LanceDBKBIndexBackend(uri=None, filesystem=dirfs)
        await backend1.ensure_ready(schema=schema)
        generated_uri = backend1._uri

        row = _row("persist1", "persistent data", "en")
        await backend1.upsert(table_name="text_chunks", rows=_aiter_one(row))

        # Second instance: use same URI to read data
        backend2 = LanceDBKBIndexBackend(uri=generated_uri, filesystem=dirfs)
        await backend2.ensure_ready(schema=schema)

        res = await backend2.search(
            query=SearchQuery(
                targets=[SearchTarget(table_name="text_chunks", vector_column="vs_a", query_vector=[1.0, 0.0])],
                limit=10,
            )
        )
        assert len(res) == 1
        assert res[0].chunk_id == row.chunk_id
        assert res[0].payload.get("text") == "persistent data"

    @pytest.mark.asyncio
    async def test_multiple_schemas_in_same_filesystem(self, tmp_path):
        """Test multiple schemas can coexist in the same filesystem."""
        base_path = str(tmp_path / "multi_schema")
        fs = filesystem("file", auto_mkdir=True)
        dirfs = DirFileSystem(path=base_path, fs=fs)

        # Schema 1
        schema1 = _schema_text()
        backend1 = LanceDBKBIndexBackend(uri=None, filesystem=dirfs)
        await backend1.ensure_ready(schema=schema1)

        row1 = _row("schema1_k1", "schema 1 data", "en")
        await backend1.upsert(table_name="text_chunks", rows=_aiter_one(row1))

        # Schema 2 (different ID)
        schema2 = KBSchema(
            id="kb-test-2",  # Different ID
            version=1,
            routing=schema1.routing,
            tables=schema1.tables,
        )
        backend2 = LanceDBKBIndexBackend(uri=None, filesystem=dirfs)
        await backend2.ensure_ready(schema=schema2)

        row2 = _row("schema2_k1", "schema 2 data", "en")
        await backend2.upsert(table_name="text_chunks", rows=_aiter_one(row2))

        # Verify URIs are different (different schema IDs)
        assert backend1._uri != backend2._uri
        assert "kb-test" in backend1._uri
        assert "kb-test-2" in backend2._uri

        # Verify data isolation
        res1 = await backend1.search(
            query=SearchQuery(
                targets=[SearchTarget(table_name="text_chunks", vector_column="vs_a", query_vector=[1.0, 0.0])],
                limit=10,
            )
        )
        assert len(res1) == 1
        assert res1[0].payload.get("text") == "schema 1 data"

        res2 = await backend2.search(
            query=SearchQuery(
                targets=[SearchTarget(table_name="text_chunks", vector_column="vs_a", query_vector=[1.0, 0.0])],
                limit=10,
            )
        )
        assert len(res2) == 1
        assert res2[0].payload.get("text") == "schema 2 data"


class TestLanceDBBackendResolver:
    """Integration tests for LanceDBKBIndexBackendResolver with filesystem injection."""

    @pytest.mark.asyncio
    async def test_resolver_with_filesystem_injection(self, tmp_path):
        """Test resolver correctly injects filesystem dependency."""
        from unittest.mock import MagicMock

        base_path = str(tmp_path / "resolver_test")
        fs = filesystem("file", auto_mkdir=True)
        dirfs = DirFileSystem(path=base_path, fs=fs)

        # Create resolver
        resolver = LanceDBKBIndexBackendResolver(uri=None)

        # Mock the inject method to return our filesystem
        resolver.inject = MagicMock(return_value=dirfs)

        # Resolve backend
        backend = resolver.resolve(org_id="test_org", guild_id="test_guild", agent_id="test_agent")

        # Verify inject was called with correct parameters
        resolver.inject.assert_called_once_with(DirFileSystem, "filesystem", "test_org", "test_guild", "test_agent")

        # Verify backend has filesystem
        assert backend._fs == dirfs
        assert backend._uri is None  # Not set until ensure_ready

        # Test it works
        schema = _schema_text()
        await backend.ensure_ready(schema=schema)

        assert backend._uri is not None
        assert "kb-test" in backend._uri

        row = _row("resolver_test", "resolver data", "en")
        await backend.upsert(table_name="text_chunks", rows=_aiter_one(row))

        res = await backend.search(
            query=SearchQuery(
                targets=[SearchTarget(table_name="text_chunks", vector_column="vs_a", query_vector=[1.0, 0.0])],
                limit=10,
            )
        )
        assert len(res) == 1
        assert res[0].payload.get("text") == "resolver data"

    @pytest.mark.asyncio
    async def test_resolver_with_explicit_uri(self, tmp_path):
        """Test resolver with explicit URI."""
        from unittest.mock import MagicMock

        base_path = str(tmp_path / "resolver_explicit")
        fs = filesystem("file", auto_mkdir=True)
        dirfs = DirFileSystem(path=base_path, fs=fs)

        explicit_uri = str(tmp_path / "explicit_db")

        # Create resolver with explicit URI
        resolver = LanceDBKBIndexBackendResolver(uri=explicit_uri)
        resolver.inject = MagicMock(return_value=dirfs)

        # Resolve backend
        backend = resolver.resolve(org_id="test_org", guild_id="test_guild", agent_id="test_agent")

        # Verify explicit URI is used
        assert backend._uri == explicit_uri

        # Test it works
        schema = _schema_text()
        await backend.ensure_ready(schema=schema)

        # URI should remain the explicit one
        assert backend._uri == explicit_uri

        row = _row("explicit_resolver", "explicit resolver data", "en")
        await backend.upsert(table_name="text_chunks", rows=_aiter_one(row))

        res = await backend.search(
            query=SearchQuery(
                targets=[SearchTarget(table_name="text_chunks", vector_column="vs_a", query_vector=[1.0, 0.0])],
                limit=10,
            )
        )
        assert len(res) == 1


class TestFilesystemURIGeneration:
    """Test URI generation from filesystem paths."""

    @pytest.mark.asyncio
    async def test_nested_filesystem_paths(self, tmp_path):
        """Test with deeply nested filesystem paths."""
        base_path = str(tmp_path / "org1" / "guild1" / "agent1" / "lancedb")
        fs = filesystem("file", auto_mkdir=True)
        fs.makedirs(base_path, exist_ok=True)
        dirfs = DirFileSystem(path=base_path, fs=fs)

        schema = _schema_text()
        backend = LanceDBKBIndexBackend(uri=None, filesystem=dirfs)
        await backend.ensure_ready(schema=schema)

        # Verify URI contains the nested path
        assert backend._uri is not None
        assert "org1" in backend._uri
        assert "guild1" in backend._uri
        assert "agent1" in backend._uri
        assert "kb-test" in backend._uri

        # Verify it works
        row = _row("nested_test", "nested path data", "en")
        await backend.upsert(table_name="text_chunks", rows=_aiter_one(row))

        res = await backend.search(
            query=SearchQuery(
                targets=[SearchTarget(table_name="text_chunks", vector_column="vs_a", query_vector=[1.0, 0.0])],
                limit=10,
            )
        )
        assert len(res) == 1

    @pytest.mark.asyncio
    async def test_schema_id_special_characters_in_uri(self, tmp_path):
        """Test schema IDs with special characters are properly encoded in URIs."""
        base_path = str(tmp_path / "special_chars")
        fs = filesystem("file", auto_mkdir=True)
        dirfs = DirFileSystem(path=base_path, fs=fs)

        # Schema with special characters in ID
        schema = KBSchema(
            id="kb-test/with-special_chars.v2",
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
                    ],
                    vector_columns=[
                        VectorSpec(name="vs_a", dim=2, distance="cosine", index=VectorIndexSpec(type="flat")),
                    ],
                    indexes=[],
                )
            ],
        )

        backend = LanceDBKBIndexBackend(uri=None, filesystem=dirfs)
        await backend.ensure_ready(schema=schema)

        # URI should be generated (special chars may be encoded)
        assert backend._uri is not None
        assert "kb-test" in backend._uri or "with-special" in backend._uri

        # Verify it works despite special characters
        row = _row("special_test", "special chars data", "en")
        await backend.upsert(table_name="text_chunks", rows=_aiter_one(row))

        res = await backend.search(
            query=SearchQuery(
                targets=[SearchTarget(table_name="text_chunks", vector_column="vs_a", query_vector=[1.0, 0.0])],
                limit=10,
            )
        )
        assert len(res) == 1
