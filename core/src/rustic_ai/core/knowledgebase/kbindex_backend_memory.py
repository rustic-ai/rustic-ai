"""In-memory StorageBackend implementation for testing and prototyping.

Not for production use. Stores rows in process memory and supports simple vector
search with cosine/dot similarity or negative L2 distance as score.
"""

import math
import re
from typing import Any, AsyncIterable, Dict, List, Optional, Sequence, Tuple

from pydantic import BaseModel

from rustic_ai.core.guild.agent_ext.depends.dependency_resolver import (
    DependencyResolver,
)

from .kbindex_backend import KBIndexBackend
from .pipeline_executor import EmittedRow
from .query import BoolFilter, FilterClause, FilterOp, SearchQuery, SearchResult
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

    async def search(self, *, query: SearchQuery) -> List[SearchResult]:  # type: ignore[override]
        if not query.targets:
            return []
        target = query.targets[0]
        table_name = target.table_name
        vector_column = target.vector_column
        limit = query.limit

        table = self._tables.get(table_name)
        vspec = self._vector_specs.get((table_name, vector_column))
        if table is None or vspec is None:
            return []

        # Determine signals
        # Prefer per-target query vector when provided
        qvec: Optional[List[float]] = None
        if getattr(query, "targets", None) and query.targets[0].query_vector is not None:
            qvec = [float(x) for x in query.targets[0].query_vector or []]
        # Global vector removed from SearchQuery; keep fallback for compatibility if present
        elif getattr(query, "vector", None) is not None:  # type: ignore[attr-defined]
            qvec = [float(x) for x in getattr(query, "vector")]  # type: ignore[index]
        qtext: Optional[str] = query.text or None

        # Sparse stats
        query_tokens, token_df, N, avgdl = self._compute_sparse_stats(table, query, qtext)

        # Collect scores
        dense_scores, sparse_scores = self._collect_scores(
            table=table,
            vspec=vspec,
            vector_column=vector_column,
            qvec=qvec,
            query_tokens=query_tokens,
            token_df=token_df,
            N=N,
            avgdl=avgdl,
            query=query,
        )

        # Merge/fuse
        out: List[Tuple[float, _RowRecord]] = []
        if query.hybrid and (qvec is not None or query_tokens):
            dw = float(query.hybrid.dense_weight)
            sw = float(query.hybrid.sparse_weight)
            if query.hybrid.fusion_strategy.value.lower() == "rrf":
                out = self._fuse_rrf(dense_scores, sparse_scores, table, dw, sw)
            else:
                out = self._fuse_linear(dense_scores, sparse_scores, table, dw, sw)
        else:
            # Single-signal fallback
            if qvec is not None and dense_scores:
                out.extend(dense_scores)
            elif query_tokens and sparse_scores:
                out.extend(sparse_scores)

        out.sort(key=lambda t: t[0], reverse=True)
        top = out[: max(1, int(limit))]
        results: List[SearchResult] = [
            SearchResult(chunk_id=rec.chunk_id, score=score, payload=dict(rec.columns)) for score, rec in top
        ]
        # Attach debug breakdown when explain=True
        if getattr(query, "explain", False):
            dense_by_id: Dict[str, float] = {rec.chunk_id: s for s, rec in dense_scores}
            sparse_by_id: Dict[str, float] = {rec.chunk_id: s for s, rec in sparse_scores}
            for r in results:
                dbg = {
                    "score_breakdown": {
                        "dense_score": dense_by_id.get(r.chunk_id),
                        "sparse_score": sparse_by_id.get(r.chunk_id),
                        "hybrid_score": r.score,
                    },
                    "distance": vspec.distance,
                }
                r.payload["_debug"] = dbg
        return results

    # ---- Helpers: filtering ----
    def _eval_bool_clause(self, rec: _RowRecord, clause: FilterClause) -> bool:
        value = rec.columns.get(clause.field)
        handlers = {
            FilterOp.EQ: self._cmp_eq,
            FilterOp.NEQ: self._cmp_ne,
            FilterOp.GT: lambda a, b: self._cmp_rel(a, b, "gt"),
            FilterOp.GTE: lambda a, b: self._cmp_rel(a, b, "ge"),
            FilterOp.LT: lambda a, b: self._cmp_rel(a, b, "lt"),
            FilterOp.LTE: lambda a, b: self._cmp_rel(a, b, "le"),
            FilterOp.IN: self._in_op,
            FilterOp.NIN: self._nin_op,
            FilterOp.EXISTS: self._exists_op,
        }
        func = handlers.get(clause.op)
        if func is None:
            return True
        return func(value, clause.value)

    # Comparison helpers split out to keep complexity low
    @staticmethod
    def _cmp_eq(a: Any, b: Any) -> bool:
        try:
            return bool(a == b)
        except Exception:
            return False

    @staticmethod
    def _cmp_ne(a: Any, b: Any) -> bool:
        try:
            return bool(a != b)
        except Exception:
            return False

    @staticmethod
    def _cmp_rel(a: Any, b: Any, which: str) -> bool:
        import operator as _op

        if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
            return False
        av: float = float(a)
        bv: float = float(b)
        ops = {"gt": _op.gt, "ge": _op.ge, "lt": _op.lt, "le": _op.le}
        try:
            return bool(ops[which](av, bv))
        except Exception:
            return False

    @staticmethod
    def _in_op(a: Any, b: Any) -> bool:
        try:
            return bool(a in b)  # type: ignore[operator]
        except Exception:
            return False

    @staticmethod
    def _nin_op(a: Any, b: Any) -> bool:
        try:
            return bool(a not in b)  # type: ignore[operator]
        except Exception:
            return False

    @staticmethod
    def _exists_op(a: Any, b: Any) -> bool:
        exists = bool(b)
        return (a is not None) if exists else (a is None)

    def _passes_filter(self, rec: _RowRecord, query: SearchQuery) -> bool:
        if not query.filter:
            return True
        bf: BoolFilter = query.filter
        for c in bf.must:
            if not self._eval_bool_clause(rec, c):
                return False
        for c in bf.must_not:
            if self._eval_bool_clause(rec, c):
                return False
        if bf.should:
            return any(self._eval_bool_clause(rec, c) for c in bf.should)
        return True

    # ---- Helpers: sparse ----
    @staticmethod
    def _tokenize(s: Optional[str]) -> List[str]:
        if not s:
            return []
        return [t for t in re.findall(r"\w+", s.lower()) if t]

    def _compute_sparse_stats(
        self,
        table: Dict[str, _RowRecord],
        query: SearchQuery,
        qtext: Optional[str],
    ) -> Tuple[List[str], Dict[str, int], int, float]:
        query_tokens: List[str] = self._tokenize(qtext)
        token_df: Dict[str, int] = {}
        doc_lengths: Dict[str, int] = {}
        if query_tokens:
            for rec in table.values():
                if not self._passes_filter(rec, query):
                    continue
                text = str(rec.columns.get("text") or "")
                toks = set(self._tokenize(text))
                doc_lengths[rec.chunk_id] = len(self._tokenize(text))
                for t in set(query_tokens) & toks:
                    token_df[t] = token_df.get(t, 0) + 1
        N = max(1, len([r for r in table.values() if self._passes_filter(r, query)]))
        avgdl = (sum(doc_lengths.values()) / max(1, len(doc_lengths))) if doc_lengths else 0.0
        return query_tokens, token_df, N, avgdl

    @staticmethod
    def _bm25_score_for_text(
        text: str, query_tokens: List[str], token_df: Dict[str, int], N: int, avgdl: float
    ) -> float:
        if not query_tokens:
            return 0.0
        k1 = 1.2
        b = 0.75
        toks = InMemoryKBIndexBackend._tokenize(text)
        if not toks:
            return 0.0
        dl = len(toks)
        tf: Dict[str, int] = {}
        for t in toks:
            tf[t] = tf.get(t, 0) + 1
        score = 0.0
        for t in set(query_tokens):
            df = token_df.get(t, 0)
            if df <= 0:
                continue
            idf = math.log((N - df + 0.5) / (df + 0.5) + 1.0)
            tfi = tf.get(t, 0)
            denom = tfi + k1 * (1 - b + b * (dl / (avgdl or 1.0)))
            score += idf * ((tfi * (k1 + 1)) / (denom or 1.0))
        return score

    # ---- Helpers: scoring ----
    def _collect_scores(
        self,
        *,
        table: Dict[str, _RowRecord],
        vspec: VectorSpec,
        vector_column: str,
        qvec: Optional[List[float]],
        query_tokens: List[str],
        token_df: Dict[str, int],
        N: int,
        avgdl: float,
        query: SearchQuery,
    ) -> Tuple[List[Tuple[float, _RowRecord]], List[Tuple[float, _RowRecord]]]:
        dense_scores: List[Tuple[float, _RowRecord]] = []
        sparse_scores: List[Tuple[float, _RowRecord]] = []
        for rec in table.values():
            if not self._passes_filter(rec, query):
                continue
            if qvec is not None:
                vec = rec.vectors.get(vector_column)
                if vec and len(vec) == len(qvec):
                    dscore = self._score(qvec, vec, vspec.distance)
                    dense_scores.append((dscore, rec))
            if query_tokens:
                text = str(rec.columns.get("text") or "")
                sscore = self._bm25_score_for_text(text, query_tokens, token_df, N, avgdl)
                sparse_scores.append((sscore, rec))
        return dense_scores, sparse_scores

    # ---- Helpers: fusion ----
    @staticmethod
    def _fuse_linear(
        dense_scores: List[Tuple[float, _RowRecord]],
        sparse_scores: List[Tuple[float, _RowRecord]],
        table: Dict[str, _RowRecord],
        dw: float,
        sw: float,
    ) -> List[Tuple[float, _RowRecord]]:
        dense_by_id: Dict[str, float] = {rec.chunk_id: s for s, rec in dense_scores}
        sparse_by_id: Dict[str, float] = {rec.chunk_id: s for s, rec in sparse_scores}
        all_ids = set(dense_by_id) | set(sparse_by_id)

        def _norm(scores: Dict[str, float]) -> Dict[str, float]:
            if not scores:
                return {}
            vmin = min(scores.values())
            vmax = max(scores.values())
            if vmax <= vmin:
                return {k: 0.0 for k in scores}
            return {k: (v - vmin) / (vmax - vmin) for k, v in scores.items()}

        dn = _norm(dense_by_id)
        sn = _norm(sparse_by_id)
        out: List[Tuple[float, _RowRecord]] = []
        for cid in all_ids:
            rec = table.get(cid)
            if not rec:
                continue
            score = dw * dn.get(cid, 0.0) + sw * sn.get(cid, 0.0)
            out.append((score, rec))
        return out

    @staticmethod
    def _fuse_rrf(
        dense_scores: List[Tuple[float, _RowRecord]],
        sparse_scores: List[Tuple[float, _RowRecord]],
        table: Dict[str, _RowRecord],
        dw: float,
        sw: float,
    ) -> List[Tuple[float, _RowRecord]]:
        all_ids = {rec.chunk_id for _, rec in dense_scores} | {rec.chunk_id for _, rec in sparse_scores}
        rrf_k = 60.0
        dense_sorted = sorted(dense_scores, key=lambda t: t[0], reverse=True)
        sparse_sorted = sorted(sparse_scores, key=lambda t: t[0], reverse=True)
        dense_rank: Dict[str, int] = {rec.chunk_id: i + 1 for i, (_, rec) in enumerate(dense_sorted)}
        sparse_rank: Dict[str, int] = {rec.chunk_id: i + 1 for i, (_, rec) in enumerate(sparse_sorted)}
        out: List[Tuple[float, _RowRecord]] = []
        for cid in all_ids:
            rec = table.get(cid)
            if not rec:
                continue
            rd = dense_rank.get(cid)
            rs = sparse_rank.get(cid)
            score = 0.0
            if rd is not None:
                score += dw * (1.0 / (rrf_k + rd))
            if rs is not None:
                score += sw * (1.0 / (rrf_k + rs))
            out.append((score, rec))
        return out

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


class InMemoryKBIndexBackendResolver(DependencyResolver[KBIndexBackend]):
    """Resolver for the in-memory KBIndexBackend (Phase-1 only)."""

    def __init__(self, backend_profile: Optional[str] = None, **kwargs):
        super().__init__()
        self.backend_profile = (backend_profile or "memory").lower()
        self.kwargs = kwargs

    def resolve(self, guild_id: str, agent_id: str) -> KBIndexBackend:  # type: ignore[override]
        return InMemoryKBIndexBackend()
