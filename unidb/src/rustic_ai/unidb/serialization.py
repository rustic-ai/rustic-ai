"""Explicit native value adapters; no reflective fallbacks or lossy stringification."""

import base64
from datetime import date, datetime, time, timedelta
import json
import math
from typing import Any

import uni_db

QUERY_METRIC_FIELDS = (
    "parse_time_ms",
    "plan_time_ms",
    "exec_time_ms",
    "total_time_ms",
    "rows_returned",
    "rows_scanned",
    "bytes_read",
    "plan_cache_hit",
    "storage_reads",
    "cache_hits",
    "branch_scans",
    "snapshot_reads",
    "index_scans",
    "index_comparisons",
    "scans_reported",
    "vector_index_scans",
    "fts_index_scans",
    "searches_reported",
    "lance_iops",
    "subquery_executions",
    "physical_plans",
    "physical_plan_time_ms",
    "shortest_path_searches",
    "shortest_path_adjacency_reads",
)


def encode(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int):
        return value if abs(value) <= 2**53 - 1 else {"$type": "int64", "value": str(value)}
    if isinstance(value, (uni_db.Vid, uni_db.Eid)):
        return {"$type": "vid" if isinstance(value, uni_db.Vid) else "eid", "value": str(int(value))}
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Non-finite numbers cannot be represented in the protocol")
        return value
    if isinstance(value, bytes):
        return {"$type": "bytes", "encoding": "base64", "value": base64.b64encode(value).decode("ascii")}
    if isinstance(value, (datetime, date, time)):
        return {"$type": type(value).__name__, "value": value.isoformat()}
    if isinstance(value, timedelta):
        return {"$type": "duration", "microseconds": str(value // timedelta(microseconds=1))}
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("Protocol object keys must be strings")
        return {key: encode(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [encode(item) for item in value]
    return _encode_native(value)


def _encode_native(value: Any) -> Any:
    if isinstance(value, uni_db.ExplainOutput):
        return {
            "plan_text": value.plan_text,
            "warnings": encode(value.warnings),
            "cost_estimates": encode(value.cost_estimates),
            "index_usage": encode(value.index_usage),
            "suggestions": encode(value.suggestions),
        }
    if isinstance(value, uni_db.ProfileOutput):
        return {
            "total_time_ms": value.total_time_ms,
            "peak_memory_bytes": encode(value.peak_memory_bytes),
            "plan_text": value.plan_text,
            "operators": encode(value.operators),
            "logical_planning_ms": value.logical_planning_ms,
            "physical_planning_ms": value.physical_planning_ms,
            "physical_plans": value.physical_plans,
        }
    if isinstance(value, uni_db.QueryMetrics):
        return {key: encode(getattr(value, key)) for key in QUERY_METRIC_FIELDS}
    if isinstance(value, uni_db.Node):
        return {"$type": "node", "id": encode(value.id), "labels": value.labels, "properties": encode(value.properties)}
    if isinstance(value, uni_db.Edge):
        return {
            "$type": "edge",
            "id": encode(value.id),
            "edge_type": value.type,
            "source": encode(value.start_id),
            "target": encode(value.end_id),
            "properties": encode(value.properties),
        }
    if isinstance(value, uni_db.Path):
        return {"$type": "path", "nodes": encode(value.nodes), "edges": encode(value.edges)}
    if isinstance(value, uni_db.Row):
        return encode(value.to_dict())
    if isinstance(value, uni_db.QueryCommandResult):
        return {"type": value.command_type, "rows": encode(value.rows)}
    if isinstance(value, uni_db.ExplainCommandResult):
        return {"type": value.command_type, "tree": encode(value.tree)}
    if isinstance(value, uni_db.AssumeCommandResult):
        return {"type": value.command_type, "results": encode(value.results), "derived": encode(value.derived)}
    if isinstance(value, uni_db.AbduceCommandResult):
        return {"type": value.command_type, "modifications": encode(value.modifications)}
    if isinstance(value, uni_db.DeriveCommandResult):
        return {"type": value.command_type, "affected": value.affected}
    if isinstance(value, uni_db.CypherCommandResult):
        return {"type": value.command_type, "rows": encode(value.rows)}
    raise TypeError(f"Unsupported native value type: {type(value).__name__}")


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def bounded(value: Any, max_bytes: int) -> Any:
    result = encode(value)
    if len(canonical(result).encode("utf-8")) > max_bytes:
        raise ValueError("Encoded result exceeds max_output_bytes")
    return result
