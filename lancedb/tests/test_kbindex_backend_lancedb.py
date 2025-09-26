from typing import AsyncIterable

import pytest

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
from rustic_ai.lancedb import LanceDBKBIndexBackend


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


@pytest.mark.asyncio
async def test_lancedb_backend_upsert_and_search(tmp_path):
    schema = _schema_text()
    be = LanceDBKBIndexBackend(uri=str(tmp_path / ".lancedb"))
    await be.ensure_ready(schema=schema)

    row = _row("k1", "hello world", "en")
    await be.upsert(table_name="text_chunks", rows=_aiter_one(row))

    res = await be.search(
        query=SearchQuery(
            targets=[SearchTarget(table_name="text_chunks", vector_column="vs_a", query_vector=[1.0, 0.0])],
            limit=10,
            filter=BoolFilter(must=[FilterClause(field="language", op=FilterOp.EQ, value="en")]),
        )
    )
    assert len(res) == 1
    assert res[0].chunk_id == row.chunk_id
    assert res[0].payload.get("author") == "alice"
    assert res[0].payload.get("language") == "en"

    # Negative filter returns empty
    res2 = await be.search(
        query=SearchQuery(
            targets=[SearchTarget(table_name="text_chunks", vector_column="vs_a", query_vector=[1.0, 0.0])],
            limit=10,
            filter=BoolFilter(must=[FilterClause(field="language", op=FilterOp.EQ, value="fr")]),
        )
    )
    assert res2 == []


@pytest.mark.asyncio
async def test_lancedb_backend_delete(tmp_path):
    schema = _schema_text()
    be = LanceDBKBIndexBackend(uri=str(tmp_path / ".lancedb"))
    await be.ensure_ready(schema=schema)

    row = _row("k2", "goodbye")
    await be.upsert(table_name="text_chunks", rows=_aiter_one(row))
    res = await be.search(
        query=SearchQuery(
            targets=[SearchTarget(table_name="text_chunks", vector_column="vs_a", query_vector=[1.0, 0.0])],
            limit=10,
        )
    )
    assert len(res) == 1

    await be.delete_by_chunk_ids(table_name="text_chunks", chunk_ids=[row.chunk_id])
    res2 = await be.search(
        query=SearchQuery(
            targets=[SearchTarget(table_name="text_chunks", vector_column="vs_a", query_vector=[1.0, 0.0])],
            limit=10,
        )
    )
    assert res2 == []


@pytest.mark.asyncio
async def test_lancedb_backend_unknown_vector_is_skipped(tmp_path):
    schema = _schema_text()
    be = LanceDBKBIndexBackend(uri=str(tmp_path / ".lancedb"))
    await be.ensure_ready(schema=schema)

    knol = Knol(id="k3", name="k3.txt", mimetype="text/plain", language="en")
    chunk = TextChunk(
        id="k3:chunkerA:0",
        knol_id="k3",
        index=0,
        producer_id="chunkerA",
        encoding="utf-8",
        content_bytes=b"x",
        language="en",
        mimetype="text/plain",
        name="k3.txt",
    )
    row = EmittedRow(chunk_id=chunk.id, knol=knol, chunk=chunk, vectors={"vs_unknown": [0.0, 0.0]})
    await be.upsert(table_name="text_chunks", rows=_aiter_one(row))

    res = await be.search(
        query=SearchQuery(
            targets=[SearchTarget(table_name="text_chunks", vector_column="vs_a", query_vector=[0.0, 1.0])],
            limit=10,
        )
    )
    assert res == []
