# Uni-DB agent

`rustic_ai.unidb.agent.UniDBAgent` provides typed database capabilities for Rustic guilds. It uses Uni-DB **5.2.1** and Python **3.13**. Domain schema, Locy rules, named operations, and transaction assertions are supplied by the application. Guild composition owns authentication, permissions, approvals, and result visibility.

This evolves Nihal's [PR 236](https://github.com/rustic-ai/rustic-ai/pull/236). All 15 original operation names remain, with a new v1 wire contract and no legacy adapters.

Read the [site agent guide](../docs/agents/unidb/index.md), [protocol reference](../docs/agents/unidb/protocol.md), and [resolver guide](../docs/dependencies/unidb/index.md) for the supported v1 contract.

## Initialize

Configure an agent-scoped `unidb` dependency using `rustic_ai.unidb.resolver.UniDBResolver`. Persistent locations resolve relative paths through an injected Rustic filesystem. Opening modes are explicit: `open_existing` (default), `create`, or `temporary`. No opening failure substitutes an empty database.

Agent properties contain `binding_id`, limits, `raw_operations_enabled` (default false), and a versioned operation catalog. Catalog parameters are closed JSON Schema objects. Bootstrap can apply user definitions to a new database or verify an existing database. Initialization completes before processor admission.

Complete GuildSpecs and message I/O are provided for:

- [Atomic supply graph import](../docs/design/uni-db-agent-examples/supply-network-init.json): checked batch, query, safe replay, changed-payload refusal.
- [Derived receivables](../docs/design/uni-db-agent-examples/receivables-init.json): exact integer cents, supplied Locy rules, native explanation, missing derivation.
- [Supplier scenario](../docs/design/uni-db-agent-examples/supplier-scenario-init.json): scratch before/after evaluation, discarded changes, guild-approved persistent execution.

Read the [detailed design](../docs/design/uni-db-agent-design.md) for configuration and complete exchanges. From the repository root, run the three native cases without an LLM:

```bash
poetry install --with dev
PYTHONPATH=unidb/src python unidb/examples/run_examples.py
```

## Messages and execution

Named requests are `DBQueryRequest`, `DBQueryPlanRequest`, `DBQueryProfileRequest`, `DBEvaluateRequest`, `DBExplainRequest`, `DBMutateRequest`, and `DBScenarioRequest`. Discovery and reconciliation use `DBHealthRequest`, `DBCapabilitiesRequest`, `DBOperationStatusRequest`, and `DBBulkStatusRequest`.

Every request carries `protocol_version: 1`, `request_id`, and `correlation_id`. Named execution also carries `operation` and `params`. Persistent effects require an `operation_id`, stable across retries; caller payloads do not supply principals or credentials.

```python
from rustic_ai.unidb.models import DBQueryRequest

# Inside a guild caller's processor; configure an output route to the database.
request = DBQueryRequest(
    request_id="query:1", correlation_id="workflow:1",
    operation="suppliers_for_product", params={"product_id": "product:digitizer"},
)
# ctx.send(request)
```

Success families contain correlated IDs, binding, a structured result, and observed metadata. Failures are typed `DBFailure` payloads emitted through `ctx.send_error`, with code, stage, and effect (`not_started`, `rolled_back`, `committed`, or `unknown`). Workflow termination belongs to the guild. A publication failure is logged; it does not produce a competing failure after delivery may have occurred.

Ordinary mutations commit their prepared receipt with the domain effect. Durable pending claims permit unknown-outcome recovery; unresolved work is never automatically reexecuted. Completed replay returns the stored result without inventing unavailable original commit metadata. Receipts are scoped by binding, runtime sender attribution, and operation ID. One authoritative write owner is supported; trusted catalogs and raw callers must preserve connector metadata.

DDL/index/flush and native bulk loads use separate bookkeeping and do not promise ordinary transaction atomicity. Bulk reconciliation preserves native load IDs and applied outcomes. Scalar/vector indexes, schema inspection, raw Cypher query/execute, and bulk vertices/edges remain available through their dedicated typed messages. Bulk edges use business external IDs; native VIDs are resolved inside the runtime.

Timeout, memory, input/output bytes, row count, and mutation statement count are bounded. Requests can only reduce configured limits. There are no automatic conflict retries. Native values use explicit serializers, including tagged identifiers and integers beyond JSON's exact number range. Explanations retain native evidence; oversized proofs fail rather than being silently trimmed.

## Query diagnostics

`DBQueryPlanRequest` and `DBQueryProfileRequest` select existing catalog operations of kind `query`. They use the same request IDs, parameters, provenance, and live-view validation as named reads. Neither requires an operation ID or creates an execution receipt.

Planning returns `executed: false` and native plan text, warnings, cost estimates, index usage, and suggestions. Uni-DB 5.2.1 plans the query template: parameter values do not specialize its estimates. The response explicitly reports `parameter_values_applied: false`, `planning_timeout_enforced: false`, and `planning_memory_enforced: false`. Only input/output byte-limit reductions are accepted for planning; other requested limits produce `unsupported_limit`.

Profiling executes the named read exactly once, enforcing native timeout and memory bounds. Its response contains `executed: true`, a bounded `query` result, and a `profile` with native operators, timing, memory, and query metrics. Empty native results can omit column names; configured catalog columns are then returned with `columns_source: catalog`. Otherwise their source is `native`. Row truncation does not erase the measurements of the complete native execution. Memory measurements are native operator figures, not process RSS.

The [query diagnostics guild](../showcase/apps/unidb_query_diagnostics.json) composes a deterministic driver with UniDB. It seeds 50 products, captures a plan/profile, adds a BTREE index, then captures both again. The lookup rows stay identical while the measured scan count changes from 50 to one. Timings are reported as observed; the example does not promise lower latency.

Run the complete guild without an LLM:

```bash
PYTHONPATH=unidb/src:showcase/src python unidb/examples/run_query_diagnostics.py
```

The runner owns a disposable temporary binding and explicitly closes the resolver before guild shutdown. Success and failure are typed terminal results; guild routes set completion/error status and produce the user presentation. Optional tool schemas are `DBQueryPlanArguments` and `DBQueryProfileArguments`; configure them in the embedding guild's toolset and routes. The existing assistant's 15 default tools remain unchanged.

## Optional LLM tools

Install the module's `tools` extra to use `UniDBToolsManagerPlugin` and `UniDBToolAdapter`. These are guild adapters; the database agent itself does not depend on an LLM. Argument schemas omit protocol identities, the adapter supplies them, and results retain the provider's actual tool-call ID and `ToolMessage` history. The [showcase](../showcase/apps/unidb_assistant.json) demonstrates one tool call per reasoning turn. Unknown or committed failure outcomes go to reconciliation without an automatic model retry.

## Validation and boundaries

The native suite tests all three cases, all retained operations, rollback/reopen/replay, commit and publication faults, interrupted bulk/admin outcomes, bounds, proof serialization, readiness failure, and scratch isolation. Guild tests exercise actual processor selection, routes, typed errors, and an illustrative guild-owned access boundary. The showcase tool loop uses a scripted LLM; production model quality and authorization need application validation.

```bash
PYTHONPATH=unidb/src:showcase/src:unidb/tests pytest unidb/tests showcase/tests/unidb
```

Scenario applicability checks and a general Rustic resource shutdown hook are deliberately deferred. The embedding owner must call `UniDBResolver.close()` before guild shutdown. Native deadlines are supported; message-driven cancellation is not advertised. Remote storage certification, multiple writers, receipt retention, pinned/fork reads, and artifact transport are outside this version's supported surface. Existing-rule verification checks the connector's bootstrap digest, not out-of-band registry mutations.
