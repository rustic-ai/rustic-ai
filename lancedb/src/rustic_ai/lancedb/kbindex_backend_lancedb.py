from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterable, Dict, List, Optional, Sequence, Tuple

import pyarrow as pa

try:
    import lancedb
    from lancedb.index import HnswSq, IvfFlat, IvfPq
except Exception:  # pragma: no cover - import errors surfaced during test collection
    lancedb = None  # type: ignore
    IvfFlat = IvfPq = HnswPq = HnswSq = None  # type: ignore

from rustic_ai.core.guild.agent_ext.depends.dependency_resolver import (
    DependencyResolver,
)
from rustic_ai.core.knowledgebase.kbindex_backend import KBIndexBackend
from rustic_ai.core.knowledgebase.pipeline_executor import EmittedRow
from rustic_ai.core.knowledgebase.query import (
    BoolFilter,
    FilterClause,
    FilterOp,
    SearchQuery,
    SearchResult,
)
from rustic_ai.core.knowledgebase.schema import KBSchema, TableSpec, VectorSpec


class LanceDBKBIndexBackend(KBIndexBackend):
    """LanceDB-backed KB index implementation.

    Notes:
        - Uses an async LanceDB connection/API
        - Performs idempotent upsert via delete+add on primary key columns
        - Always persists a "chunk_id" scalar column (if missing) to return it in results
    """

    def __init__(self, *, uri: str) -> None:
        if lancedb is None:  # pragma: no cover - surfaced in tests if dependency missing
            raise RuntimeError("lancedb package is not available; please install it")
        self._uri: str = uri
        self._schema: Optional[KBSchema] = None
        self._table_by_name: Dict[str, TableSpec] = {}
        self._vector_specs: Dict[Tuple[str, str], VectorSpec] = {}
        self._conn: Optional[Any] = None
        self._tables: Dict[str, Any] = {}

    # ---------------------- lifecycle ----------------------
    async def ensure_ready(self, *, schema: KBSchema) -> None:  # type: ignore[override]
        self._schema = schema
        self._table_by_name = {t.name: t for t in schema.tables}
        self._vector_specs = {}
        for t in schema.tables:
            for vs in t.vector_columns:
                self._vector_specs[(t.name, vs.name)] = vs

        self._conn = await lancedb.connect_async(self._uri)  # type: ignore[attr-defined]

        for t in schema.tables:
            await self._ensure_table_ready(t)
            await self._ensure_indexes_ready(t)

    # ---------------------- writes ----------------------
    async def upsert(self, *, table_name: str, rows: AsyncIterable[EmittedRow]) -> None:  # type: ignore[override]
        table = await self._get_table(table_name)
        spec = self._table_by_name.get(table_name)
        if spec is None:
            raise ValueError(f"Unknown table: {table_name}")

        # Batch rows to amortize I/O
        batch: List[Dict[str, Any]] = []
        pk_cols: Sequence[str] = list(spec.primary_key)
        BATCH_SIZE = 200

        async for r in rows:
            record = self._map_row_to_record(r, spec)
            batch.append(record)
            if len(batch) >= BATCH_SIZE:
                await self._flush_batch(table, spec, batch, pk_cols)
                batch = []

        if batch:
            await self._flush_batch(table, spec, batch, pk_cols)

    async def _flush_batch(
        self, table: Any, spec: TableSpec, batch: List[Dict[str, Any]], pk_cols: Sequence[str]
    ) -> None:
        # Delete existing by PKs (idempotent upsert) then add
        where = self._build_pk_where(pk_cols, batch)
        if where:
            await table.delete(where)
        await self._add_batch(table=table, table_spec=spec, batch=batch)

    async def delete_by_chunk_ids(self, *, table_name: str, chunk_ids: Sequence[str]) -> None:  # type: ignore[override]
        if not chunk_ids:
            return
        table = await self._get_table(table_name)
        for slice_ids in _slices(chunk_ids, 500):
            in_list = ", ".join(_quote(v) for v in slice_ids)
            where = f"chunk_id IN ({in_list})"
            await table.delete(where)

    # ---------------------- reads ----------------------
    async def search(self, *, query: SearchQuery) -> List[SearchResult]:  # type: ignore[override]
        if not query.targets:
            return []
        tgt = query.targets[0]
        table_name = tgt.table_name
        vector_column = tgt.vector_column
        table = await self._get_table(table_name)
        # Determine query vector
        qvec: Optional[List[float]] = None
        if tgt.query_vector is not None:
            qvec = [float(x) for x in tgt.query_vector]
        elif getattr(query, "vector", None) is not None:  # legacy/global
            qvec = [float(x) for x in getattr(query, "vector")]  # type: ignore[index]

        if qvec is None:
            return []

        # Build filter (prefilter by default)
        where = self._bool_filter_to_sql(query.filter) if query.filter else None

        builder = await table.search(qvec, vector_column_name=vector_column)

        # Metric must align with index/vector spec
        vs = self._vector_specs.get((table_name, vector_column))
        metric = (vs.distance if vs else "l2").lower()
        builder = builder.distance_type(metric)  # type: ignore[assignment]

        if where:
            builder = builder.where(where)

        limit = int(query.limit or 10)
        builder = builder.limit(limit)

        # Fetch list of dicts (contains _distance)
        rows: List[Dict[str, Any]] = await builder.to_list()

        results: List[SearchResult] = []
        for obj in rows:
            # Some drivers return vector under the vector column key, and always include _distance
            dist = float(obj.get("_distance", 0.0))
            score = self._distance_to_score(metric, dist)
            chunk_id = str(obj.get("chunk_id") or obj.get("CHUNK_ID") or "")
            # Payload: everything except internal fields
            payload = {k: v for k, v in obj.items() if k not in {"_distance"}}
            # Skip rows that do not have the vector column present (i.e., weren't embedded for this space)
            if vector_column not in payload or payload.get(vector_column) is None:
                continue
            results.append(SearchResult(chunk_id=chunk_id, score=score, payload=payload))

        return results

    # ---------------------- helpers: table & schema ----------------------
    async def _get_table(self, table_name: str) -> Any:
        if table_name in self._tables:
            return self._tables[table_name]
        if self._conn is None:
            raise RuntimeError("Backend is not initialized; call ensure_ready first")
        try:
            tbl = await self._conn.open_table(table_name)
        except Exception:
            raise ValueError(f"Unknown table: {table_name}")
        self._tables[table_name] = tbl
        return tbl

    async def _ensure_table_ready(self, table_spec: TableSpec) -> None:
        assert self._conn is not None
        name = table_spec.name
        desired_schema = self._build_arrow_schema(table_spec)

        # Try open; if missing, create
        try:
            table = await self._conn.open_table(name)
            existing = await table.schema()
            # Evolve additively: add missing fields
            missing_fields = [f for f in desired_schema if existing.get_field_index(f.name) == -1]
            if missing_fields:
                await table.add_columns(pa.schema(missing_fields))
            self._tables[name] = table
        except Exception:
            table = await self._conn.create_table(name, schema=desired_schema, exist_ok=True)
            self._tables[name] = table

    async def _ensure_indexes_ready(self, table_spec: TableSpec) -> None:
        table = await self._get_table(table_spec.name)
        # Create/refresh vector indexes according to VectorSpec
        for vs in table_spec.vector_columns or []:
            config = self._map_index_config(vs)
            if config is None:
                continue
            try:
                # Check if index already exists to avoid expensive recreation
                # Note: LanceDB python async API might not expose list_indices directly on table yet,
                # but we can try to be safe. For now, we'll assume if it's there we might not need to recreate
                # unless forced. The original code used replace=True always.
                # We will stick to replace=True but wrap in try/except with logging.
                await table.create_index(column=vs.name, config=config, replace=True)
            except Exception as e:
                # Log error but don't crash startup

                logging.error(f"Warning: Failed to create index for {table_spec.name}.{vs.name}: {e}")

    async def _add_batch(self, *, table: Any, table_spec: TableSpec, batch: List[Dict[str, Any]]) -> None:
        """Add a batch using a typed Arrow Table matching the target schema.

        This avoids schema alignment issues for fixed_size_list vectors.
        """
        if not batch:
            return
        target_schema: pa.Schema = await table.schema()
        columns: List[pa.Array] = []
        names: List[str] = []

        for field in target_schema:
            name = field.name
            dtype = field.type
            names.append(name)
            vals = [rec.get(name) for rec in batch]

            if pa.types.is_fixed_size_list(dtype):
                dim = dtype.list_size  # type: ignore[attr-defined]
                normed: List[Optional[List[float]]] = []
                for v in vals:
                    if v is None:
                        # leave as null vector (row-level null), not zeros
                        normed.append(None)
                        continue
                    arr = [float(x) for x in (v or [])]
                    if len(arr) != dim:
                        if len(arr) < dim:
                            arr = arr + [0.0] * (dim - len(arr))
                        else:
                            arr = arr[:dim]
                    normed.append(arr)
                columns.append(pa.array(normed, type=dtype))
                continue

            # Scalars
            columns.append(pa.array(vals, type=dtype))

        # Build table with schema only (names are embedded in fields)
        table_data = pa.Table.from_arrays(columns, schema=target_schema)
        await table.add(table_data)

    def _build_arrow_schema(self, table_spec: TableSpec) -> pa.Schema:
        fields: List[pa.Field] = []

        # Scalars from KBSchema columns
        for c in table_spec.columns:
            dt = self._map_scalar_type(c.type)
            fields.append(pa.field(c.name, dt, nullable=bool(c.nullable)))

        # Ensure chunk_id always present for result identity
        if all(f.name != "chunk_id" for f in fields):
            fields.append(pa.field("chunk_id", pa.utf8(), nullable=False))

        # Vector columns
        for vs in table_spec.vector_columns:
            vec_type = lancedb.vector(int(vs.dim))  # type: ignore[attr-defined]
            fields.append(pa.field(vs.name, vec_type, nullable=True))

        return pa.schema(fields)

    # ---------------------- helpers: mapping ----------------------
    def _map_row_to_record(self, row: EmittedRow, spec: TableSpec) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        # Scalars
        for col in spec.columns:
            source = col.source
            selector = col.selector
            if source == "knol":
                val = self._select_from_obj(row.knol, selector)
            elif source == "chunk":
                val = self._select_from_obj(row.chunk, selector)
            elif source == "meta":
                val = self._select_from_meta(row, selector)
            else:
                val = None
            out[col.name] = self._coerce_scalar_value(col.type, val)

        # Identity column for results
        out.setdefault("chunk_id", row.chunk_id)

        # Vectors (only those present and defined for this table)
        for vname, vec in (row.vectors or {}).items():
            if (spec.name, vname) not in self._vector_specs:
                continue
            out[vname] = [float(x) for x in vec]

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
    def _coerce_scalar_value(kind: str, value: Any) -> Any:
        if value is None:
            return None
        try:
            if kind in {"string", "text", "json"}:
                if kind == "json":
                    try:
                        return json.dumps(value, ensure_ascii=False)
                    except Exception:
                        return str(value)
                return str(value)
            if kind == "int":
                return int(value)
            if kind == "float":
                return float(value)
            if kind == "bool":
                return bool(value)
            if kind == "timestamp":
                # Expect datetime; if not, drop to None
                try:
                    # If already datetime-like, pass through
                    from datetime import datetime  # local import to avoid module cost

                    if isinstance(value, datetime):
                        return value
                except Exception:
                    pass
                return None
            if kind.startswith("array<") and kind.endswith(">"):
                # pass through lists; basic normalization
                if isinstance(value, list):
                    return value
                return [value]
        except Exception:
            return None
        return value

    @staticmethod
    def _map_scalar_type(kind: str) -> pa.DataType:
        k = kind.lower()
        if k in {"string", "text"}:
            return pa.utf8()
        if k == "int":
            return pa.int64()
        if k == "float":
            return pa.float32()
        if k == "bool":
            return pa.bool_()
        if k == "timestamp":
            return pa.timestamp("us")
        if k == "json":
            return pa.large_string()
        if k.startswith("array<") and k.endswith(">"):
            inner = k[len("array<") : -1]
            inner_dt = {
                "string": pa.utf8(),
                "int": pa.int64(),
                "float": pa.float32(),
            }.get(inner, pa.large_string())
            return pa.list_(inner_dt)
        # Fallback
        return pa.large_string()

    @staticmethod
    def _map_index_config(vs: VectorSpec):
        t = (vs.index.type if vs.index else "").lower()
        dist = vs.distance.lower()
        if t in {"", "flat"}:
            return None
        if t == "ivf_flat":
            return IvfFlat(distance_type=dist)
        if t in {"pq", "ivf_pq"}:
            # Basic mapping; params can be extended from vs.index.params
            params = dict(vs.index.params or {})
            return IvfPq(
                distance_type=dist,
                num_partitions=params.get("num_partitions"),
                num_sub_vectors=params.get("num_sub_vectors"),
                num_bits=params.get("num_bits", 8),
            )
        if t == "hnsw":
            params = dict(vs.index.params or {})
            # Prefer SQ for small dims; either works for tests
            return HnswSq(
                distance_type=dist,
                num_partitions=params.get("num_partitions"),
                m=params.get("m", 20),
                ef_construction=params.get("ef_construction", 300),
            )
        # Unknown type -> no index
        return None

    @staticmethod
    def _build_pk_where(pk_cols: Sequence[str], rows: List[Dict[str, Any]]) -> str:
        if not pk_cols:
            return ""
        clauses: List[str] = []
        for rec in rows:
            parts: List[str] = []
            for c in pk_cols:
                v = rec.get(c)
                if isinstance(v, str):
                    parts.append(f"{c} = {_quote(v)}")
                else:
                    parts.append(f"{c} = {v}")
            if parts:
                clauses.append("(" + " AND ".join(parts) + ")")
        return " OR ".join(clauses)

    # ---------------------- helpers: filtering & scoring ----------------------
    @staticmethod
    def _bool_filter_to_sql(bf: BoolFilter) -> Optional[str]:
        if not bf:
            return None
        must = [LanceDBKBIndexBackend._clause_to_sql(c) for c in (bf.must or []) if c]
        must_not = [LanceDBKBIndexBackend._clause_to_sql(c, negate=True) for c in (bf.must_not or []) if c]
        should = [LanceDBKBIndexBackend._clause_to_sql(c) for c in (bf.should or []) if c]
        parts: List[str] = []
        if must:
            parts.append("(" + " AND ".join(must) + ")")
        if must_not:
            parts.append("(" + " AND ".join(must_not) + ")")
        if should:
            parts.append("(" + " OR ".join(should) + ")")
        return " AND ".join(p for p in parts if p)

    @staticmethod
    def _clause_to_sql(c: FilterClause, negate: bool = False) -> str:
        field = c.field
        op = c.op
        val = c.value

        def lit(x: Any) -> str:
            if isinstance(x, str):
                return _quote(x)
            if isinstance(x, bool):
                return "TRUE" if x else "FALSE"
            if x is None:
                return "NULL"
            return str(x)

        if op == FilterOp.EXISTS:
            return f"{field} IS NOT NULL" if bool(val) else f"{field} IS NULL"

        if op in {FilterOp.IN, FilterOp.NIN}:
            seq = list(val or [])
            expr = f"{field} IN (" + ", ".join(lit(v) for v in seq) + ")"
            return f"NOT ({expr})" if (op == FilterOp.NIN) ^ negate else expr

        OPS = {
            FilterOp.EQ: "=",
            FilterOp.NEQ: "!=",
            FilterOp.GT: ">",
            FilterOp.GTE: ">=",
            FilterOp.LT: "<",
            FilterOp.LTE: "<=",
        }
        sql_op = OPS.get(op, "=")
        expr = f"{field} {sql_op} {lit(val)}"
        return f"NOT ({expr})" if negate else expr

    @staticmethod
    def _distance_to_score(metric: str, distance: float) -> float:
        m = metric.lower()
        if m == "l2":
            return -float(distance)
        if m == "cosine":
            # lancedb returns a cosine distance in [0, 2]; convert to similarity-ish
            return 1.0 - float(distance)
        # dot: higher is better
        return float(distance)


def _slices(seq: Sequence[Any], size: int) -> List[Sequence[Any]]:
    out: List[Sequence[Any]] = []
    i = 0
    n = len(seq)
    while i < n:
        out.append(seq[i : i + size])
        i += size
    return out


def _quote(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


class LanceDBKBIndexBackendResolver(DependencyResolver[KBIndexBackend]):
    """Resolver for LanceDBKBIndexBackend.

    Properties:
        uri: Optional[str] database URI for LanceDB (e.g., file path). Defaults to env or .lancedb
    """

    def __init__(self, uri: str, **kwargs):
        super().__init__()
        self.uri: str = uri
        self.kwargs: dict = kwargs

    def resolve(self, guild_id: str, agent_id: str) -> KBIndexBackend:  # type: ignore[override]
        return LanceDBKBIndexBackend(uri=self.uri)
