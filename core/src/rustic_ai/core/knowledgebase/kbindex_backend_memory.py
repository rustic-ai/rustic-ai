"""In-memory StorageBackend implementation for testing and prototyping.

Not for production use. Stores rows in process memory and supports simple vector
search with cosine/dot similarity or negative L2 distance as score.
"""

from __future__ import annotations

import math
from typing import Any, AsyncIterable, Dict, List, Optional, Sequence, Tuple

from pydantic import BaseModel

from .kbindex_backend import KBIndexBackend, SearchResult
from .pipeline_executor import EmittedRow
from .schema import KBSchema, TableSpec, VectorSpec


class _RowRecord(BaseModel):
    chunk_id: str
    columns: Dict[str, Any]
    vectors: Dict[str, List[float]]


class InMemoryKBIndexBackend(KBIndexBackend):
    def __init__(self) -> None:
        self._schema: Optional[KBSchema] = None
        self._table_by_name: Dict[str, TableSpec] = {}
        self._tables: Dict[str, Dict[str, _RowRecord]] = {}
        self._vector_specs: Dict[Tuple[str, str], VectorSpec] = {}

    async def ensure_ready(self, *, schema: KBSchema) -> None:  # type: ignore[override]
        self._schema = schema
        self._table_by_name = {t.name: t for t in schema.tables}
        # Initialize empty tables and cache vector specs
        for t in schema.tables:
            if t.name not in self._tables:
                self._tables[t.name] = {}
            for vs in t.vector_columns:
                self._vector_specs[(t.name, vs.name)] = vs

    async def upsert(self, *, table_name: str, rows: AsyncIterable[EmittedRow]) -> None:  # type: ignore[override]
        table = self._tables.get(table_name)
        spec = self._table_by_name.get(table_name)
        if table is None or spec is None:
            raise ValueError(f"Unknown table: {table_name}")

        async for r in rows:
            # Map scalar columns from EmittedRow via ColumnSpec
            cols: Dict[str, Any] = {}
            for col in spec.columns:
                source = col.source
                sel = col.selector
                if source == "knol":
                    value = self._select_from_obj(r.knol, sel)
                elif source == "chunk":
                    value = self._select_from_obj(r.chunk, sel)
                elif source == "meta":
                    value = self._select_from_meta(r, sel)
                else:
                    value = None
                cols[col.name] = value

            # Map vector columns present in the row
            vecs: Dict[str, List[float]] = {}
            for vname, v in r.vectors.items():
                if (table_name, vname) not in self._vector_specs:
                    continue  # skip unknown vector names
                vecs[vname] = [float(x) for x in v]

            table[r.chunk_id] = _RowRecord(chunk_id=r.chunk_id, columns=cols, vectors=vecs)

    async def delete_by_chunk_ids(self, *, table_name: str, chunk_ids: Sequence[str]) -> None:  # type: ignore[override]
        table = self._tables.get(table_name)
        if table is None:
            return
        for cid in chunk_ids:
            table.pop(cid, None)

    async def search(
        self,
        *,
        table_name: str,
        vector_column: str,
        query_vector: List[float],
        limit: int = 20,
        filter: Optional[Any] = None,
    ) -> List[SearchResult]:  # type: ignore[override]
        table = self._tables.get(table_name)
        vspec = self._vector_specs.get((table_name, vector_column))
        if table is None or vspec is None:
            return []

        # Build simple equality filter over scalar columns if filter is a dict
        def passes_filter(rec: _RowRecord) -> bool:
            if filter is None:
                return True
            if isinstance(filter, dict):
                for k, v in filter.items():
                    if rec.columns.get(k) != v:
                        return False
                return True
            return True

        q = [float(x) for x in query_vector]
        out: List[Tuple[float, _RowRecord]] = []
        for rec in table.values():
            if not passes_filter(rec):
                continue
            vec = rec.vectors.get(vector_column)
            if not vec:
                continue
            score = self._score(q, vec, vspec.distance)
            out.append((score, rec))

        out.sort(key=lambda t: t[0], reverse=True)
        top = out[: max(1, int(limit))]
        return [SearchResult(chunk_id=rec.chunk_id, score=score, payload=dict(rec.columns)) for score, rec in top]

    @staticmethod
    def _select_from_obj(obj: Any, selector: str) -> Any:
        cur: Any = obj
        for part in selector.split(".") if selector else []:
            if hasattr(cur, part):
                cur = getattr(cur, part)
            elif isinstance(cur, dict):
                cur = cur.get(part)
            else:
                return None
        return cur

    @staticmethod
    def _select_from_meta(row: EmittedRow, selector: str) -> Any:
        meta = row.knol.metadata_consolidated or {}
        cur: Any = meta
        for part in selector.split(".") if selector else []:
            if isinstance(cur, dict):
                cur = cur.get(part)
            else:
                return None
        return cur

    @staticmethod
    def _score(q: List[float], x: List[float], distance: str) -> float:
        if distance == "cosine":
            return InMemoryKBIndexBackend._cosine(q, x)
        if distance == "dot":
            return sum(a * b for a, b in zip(q, x))
        # l2 -> negative distance so that higher is better
        return -math.sqrt(sum((a - b) ** 2 for a, b in zip(q, x)))

    @staticmethod
    def _cosine(a: List[float], b: List[float]) -> float:
        num = sum(x * y for x, y in zip(a, b))
        da = math.sqrt(sum(x * x for x in a))
        db = math.sqrt(sum(y * y for y in b))
        if da <= 0.0 or db <= 0.0:
            return 0.0
        return num / (da * db)


__all__ = [
    "InMemoryKBIndexBackend",
]
