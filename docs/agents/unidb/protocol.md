# Uni-DB message protocol

All formats below live in `rustic_ai.unidb.models`. Use fully qualified format names in JSON GuildSpecs, for example `rustic_ai.unidb.models.DBQueryRequest`. Models forbid extra fields.

## Common contract

Every request has `protocol_version: 1`, a nonempty `request_id`, a nonempty `correlation_id`, and optional `limits`. Keep correlation stable for the enclosing workflow and request IDs distinct for its invocations. Persistent effects also require `operation_id`, stable across retries.

Named requests have `operation`, `params`, and optional `view`. The operation must exist in the configured catalog and match the request kind. Parameters are validated against closed JSON Schema objects before execution; values are bound through the native API. Named reads use the live view; scenarios supply scratch isolation. Pinned/fork views are not supported by this integration.

| Request | Success response | Catalog kind / purpose |
| --- | --- | --- |
| `DBQueryRequest` | `DBQueryResponse` | `query`: named Cypher read |
| `DBQueryPlanRequest` | `DBQueryPlanResponse` | `query`: native plan without executing the query |
| `DBQueryProfileRequest` | `DBQueryProfileResponse` | `query`: one native read with execution measurements |
| `DBEvaluateRequest` | `DBEvaluateResponse` | `evaluate`: supplied Locy program |
| `DBExplainRequest` | `DBExplainResponse` | `explain`: native Locy derivation evidence |
| `DBMutateRequest` | `DBMutateResponse` | `mutation`: statements and pre/post checks in one transaction |
| `DBScenarioRequest` | `DBScenarioResponse` | `scenario`: before/after evaluation with scratch changes discarded |
| `DBHealthRequest` | `DBHealthResponse` | Runtime readiness and observed health |
| `DBCapabilitiesRequest` | `DBCapabilitiesResponse` | Catalog operations, native version, views, diagnostics bounds |
| `DBOperationStatusRequest` | `DBOperationStatusResponse` | Reconcile an `operation_id` under the same sender attribution |
| `DBBulkStatusRequest` | `DBBulkStatusResponse` | Reconcile a native `load_id` |

Success responses carry the common identities, `binding_id`, `outcome: succeeded`, a structured `result`, and `metadata`. Native values have explicit serializers, including tagged VIDs/EIDs, large integers, bytes, and temporal values. Consumers must preserve those tags when JSON cannot represent a value exactly.

## Dedicated operations

These retained operation families also use the v1 identity/error contract. Each request has a correspondingly named `Response` class.

| Requests | Purpose |
| --- | --- |
| `CreateLabelRequest`, `CreateEdgeTypeRequest`, `AddPropertyRequest` | Schema administration |
| `CreateScalarIndexRequest`, `CreateVectorIndexRequest` | Index creation; scalar type `btree`, vector metric `cosine` or `l2` |
| `ListLabelsRequest`, `ListEdgeTypesRequest`, `GetLabelInfoRequest`, `GetSchemaRequest` | Schema inspection |
| `QueryRequest`, `ExecuteRequest` | Raw Cypher; requires `raw_operations_enabled: true` |
| `FlushRequest` | Native flush |
| `VectorSearchRequest` | Vector lookup with optional parameterized filter |
| `InsertVerticesRequest`, `InsertEdgesRequest` | Native bulk ingestion; edges use business external IDs |

Schema/index changes, raw execute, flush, and bulk ingestion require `operation_id`. Enabling raw operations is a capability configuration; guild policy still decides who may invoke them.

## Bounds

Requests can reduce configured bounds and cannot raise them. Defaults in `Limits` are:

| Limit | Default |
| --- | --- |
| `timeout_ms` | 5,000 |
| `max_query_memory_bytes` | 67,108,864 |
| `max_rows` | 100 |
| `max_input_bytes` | 65,536 |
| `max_output_bytes` | 65,536 |
| `max_statements` | 16 |
| `max_conflict_retries` | 0 |

Native deadline/memory bounds apply to supported execution paths. A row limit bounds returned rows, rather than necessarily the total native work. Oversized serialized output fails instead of silently dropping proof or diagnostic evidence. Native memory metrics describe operator measurements, not process RSS. There is no automatic conflict retry.

## Plan and profile

```python
from rustic_ai.unidb.models import DBQueryPlanRequest, DBQueryProfileRequest

plan = DBQueryPlanRequest(
    request_id="plan:1", correlation_id="comparison:1",
    operation="find_product", params={"name": "widget:12"},
)
profile = DBQueryProfileRequest(
    request_id="profile:1", correlation_id="comparison:1",
    operation="find_product", params={"name": "widget:12"},
    limits={"max_rows": 1},
)
```

Plan results have `executed: false` and `plan` containing native `plan_text`, `warnings`, `cost_estimates`, `index_usage`, and `suggestions`. In Uni-DB **6.0.0**, estimates use the query template: `parameter_values_applied`, `planning_timeout_enforced`, and `planning_memory_enforced` are all false. Only input/output byte-limit reductions are accepted for plan requests; requesting other valid bounds returns `unsupported_limit`. Do not infer planning limits from ordinary query limits.

Profile results have `executed: true`, a bounded `query`, and a `profile` containing operators, timings, memory, and `query_metrics`. The native read runs exactly once and rejects writes. Empty native results can omit columns; catalog columns are then returned with `columns_source: catalog`, otherwise `native`. Returned row truncation leaves complete-execution metrics intact.

Both diagnostics select existing `query` operations and create no effect receipt. Query planning is separate from `DBExplainRequest`, which exposes Locy derivation evidence.

## Errors and recovery

Failures are `DBFailure` sent through `ctx.send_error`. Its `error` contains `code`, `stage`, `retryable`, `effect`, `message`, and `details`. Common diagnostic stages are `plan`, `profile`, and `serialize`. Requests rejected before effects use `not_started`.

| Effect | Caller action |
| --- | --- |
| `not_started` | Correct rejected input/configuration; apply guild retry policy |
| `rolled_back` | No persistent domain effect from the failed transaction; a retry remains a caller decision |
| `committed` | Reconcile the persistent effect; do not blindly redispatch |
| `unknown` | Reconcile operation/load status before deciding what to do next |

An ordinary mutation commits its completed receipt in the same transaction as its domain effect, following a durable pending claim. Receipt identity uses binding, runtime sender attribution, and operation ID. Identical completed replay returns the stored result; a changed payload under the same identity is refused. Unresolved pending work is never automatically reexecuted. Replay does not invent original commit metadata that is unavailable.

DDL, index, flush, and bulk bookkeeping has separate non-atomic boundaries. A failed admin/bulk invocation can have an applied or uncertain effect. Bulk status preserves native load IDs and applied outcomes.

Rustic adds error-topic delivery; matching routing-slip rules can add further deliveries. Consumers must tolerate duplicate delivery. The guild decides whether an error is recoverable or terminal and sets `process_status` accordingly. Exactly one logical database outcome is not an exactly-once wire-delivery promise.

## Agents as tools

The optional `tools` extra provides `UniDBToolsManagerPlugin`, `UniDBToolAdapter`, and argument-only schemas in `rustic_ai.unidb.tools`. Select the families that belong in the embedding guild's toolset and add argument/request/response routes.

The argument models omit protocol and operation identities; the adapter supplies them. It preserves the model provider's actual tool-call ID and accumulated `ToolMessage` history. The bridge supports one invocation per reasoning turn and stops model continuation for `unknown` or `committed` failures, returning a reconciliation presentation.

The checked-in assistant declares the 15 retained tools. Named capability schemas, including `DBQueryPlanArguments` and `DBQueryProfileArguments`, are available for explicitly configured toolsets. The database agent remains usable without this conversational bridge.

See the [agent guide](index.md), [resolver configuration](../../dependencies/unidb/index.md), and [complete design](../../design/uni-db-agent-design.md).
