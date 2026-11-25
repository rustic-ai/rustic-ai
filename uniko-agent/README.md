# Uniko Memory Agent

Comprehensive memory agent for Rustic AI that integrates [uniko](https://github.com/rustic-ai/uniko)'s cognitive memory system.

## Overview

The Uniko Memory Agent integrates uniko's memory system into the Rustic AI guild framework. Current coverage, known gaps and acceptance gates are tracked in the [implementation and completion plan](../docs/design/uniko-agent-completion.md). It enables:

- **Local knowledge ingestion** (local ONNX models, no hosted generation API required)
- **Multi-phase recall** (3-phase cascade: Facts/Procedures → Episodes/Observations → Chunks)
- **Attributed recall and source navigation** (native provenance and explicit legacy limitations)
- **Agent-scoped storage** (each resolver instance uses the agent’s private filesystem)

Uniko stores raw messages, actions and source artifacts, then derives observations,
bitemporal facts and reusable procedures with provenance. Extraction runs at
write time through rules, code parsing and local NLP; recall combines compact
knowledge, episodic expansion and chunk search. uni-xervo owns the model runtime,
provider selection and inference behind stable task aliases. Uniko owns memory
semantics and the graph; Rustic owns message routing, sessions and dependency
lifecycle. Streaming enables background ingest/consolidation workers; direct
observation and explicit consolidation are available without streaming.

## Installation

This integration supports Uniko 0.6.0 through the 0.6 release series.
The embedded `mistralrs` runtime is no longer supported. Old `alias: mistral`
configurations are rejected; they are not migrated to the hosted Mistral API.
The base `uniko` wheel runs local ONNX memory models on CPU. Uniko also
publishes mutually exclusive `uniko-metal` (macOS ARM64) and `uniko-cuda`
(Linux x86-64) distributions; install one runtime distribution per environment.
Rustic's published dependency profile selects the CPU `uniko` distribution.
Rustic Metal/CUDA dependency profiles are unavailable in this release; the
upstream wheels are documented for future platform validation.

```bash
cd rustic-ai/uniko-agent
poetry install --with dev
```

## Quick Start

Read the [site agent guide](../docs/agents/uniko/index.md) for a complete local guild example using the current builders, typed routes, and explicit resolver shutdown. See the [message protocol](../docs/agents/uniko/protocol.md) and [resolver guide](../docs/dependencies/uniko/index.md) for every supported family and deployment option.

Inside an existing caller processor, observe and recall through configured guild routes:

```python
from rustic_ai.uniko_agent import MemoryRecordKind, MemoryScope, ObserveTurnRequest, RecallRequest

observation = ObserveTurnRequest(
    session_id="research:1", sender_id="researcher", message_id="turn:1",
    content="The pilot recovered 90% of its lithium.",
)
recall = RecallRequest(
    query="Lithium recovery rate", scope=MemoryScope(sessions=["research:1"]),
    allowed_record_kinds=[MemoryRecordKind.CONVERSATION_TURN],
)
# ctx.send(observation), wait for ObserveResult, then ctx.send(recall).
# The real caller's routes deliver both formats to the memory agent.
```

## Processor families

The current integration includes observation/typed records, document ingestion,
scoped recall, source navigation, native answers, deletion/finalization,
diagnostics, structured tool/action/episode/fact operations, atomic memory units,
goals/tasks, procedures, rules, and operation reconciliation. The
[protocol reference](../docs/agents/uniko/protocol.md) lists their request/response
formats and failure boundaries; a historical processor count is not the current API.

## Configuration

### MemoryAgentConfig

```python
from rustic_ai.uniko_agent import MemoryAgentConfig

config = MemoryAgentConfig(
    default_session_id=None,        # Defaults to guild_id
    recall_max_tokens=None,          # Preserve native settings unless explicitly overridden
    recall_phase1_only=False,        # True is unsupported and rejected
    auto_flush=True,                 # Legacy compatibility setting; direct observe needs no flush
    max_source_bytes=16 * 1024 * 1024,
    max_attachments=32,
    max_batch_items=128,
)
```

### UnikoResolver Properties

```python
{
    "storage_path": str | None,      # None = in-memory; otherwise agent-filesystem location
    "llm_spec": dict | None,         # LLM config for answer generation
    "streaming": bool,               # Enable streaming mode
    "scope_to_agent": bool,          # Restrict visibility to the Uniko agent
    "config": dict | None,           # Partial native Uniko config
    "embedding": str | dict | None,  # Native preset/section; overrides config.embedding
    "nlp": str | dict | None,        # Native preset/section; overrides config.nlp
    "reranker": str | dict | bool | None,  # False disables; None keeps defaults
}
```

### Model selection and execution modes

Ingestion, extraction, consolidation and recall work without an LLM. Uniko
uses uni-xervo model aliases for their separate tasks: `embed/default`,
`nlp/default`, and the configured reranker. The resolver passes model settings
to the native SDK, which validates them and supplies its own defaults.

```python
properties = {
    "embedding": "bge-small",  # Also nomic, nomic-q, minilm, bge-large, bge-m3, gemma
    "nlp": "v1",  # Also v7-tiny/small/medium/large/xlarge/xlarge-d
    "reranker": "minilm",  # Also bge-base, a partial config, or False
    "config": {"recall_limit": 10},
    "llm_spec": {
        "provider": "llamacpp",
        "alias": "answer/local",
        "model_id": "qwen",  # The model served by your llama-server
        "base_url": "http://127.0.0.1:8080/v1",
        # "key_env": "LLAMA_SERVER_KEY",  # Only for authenticated servers
    },
}
```

Generation supports the Python SDK's modes: `openai` (default key env),
`openai_with_key_env`, `llamacpp`, and `generic`. `alias` is a runtime model name, separate
from `provider`; `model_id` is passed through without a Rustic model whitelist.
OpenAI modes accept an optional `base_url` for compatible endpoints. llama.cpp
runs in a separate `llama-server` process, so it works with the CPU wheel too.
The established `alias: openai` input remains supported.

For advanced memory models, use partial sections such as
`embedding={"provider": "remote/openai", "model_id": "text-embedding-3-small",
"dimensions": 1536, "provider_options": {"api_key_env": "OPENAI_API_KEY"}}`,
or `config={"catalog_path": "/absolute/path/catalog.json"}`. A custom catalog
replaces the default catalog; include the aliases needed by Uniko's pipelines.
The optional `llm_spec` entry is appended separately. Changing embedding
dimensions requires a fresh store; GPU providers require a compatible wheel.

uni-xervo supports additional providers, including `remote/mistral`, Anthropic,
Gemini, Cohere and others. These can serve supported tasks through the catalog
when compiled into the runtime. Uniko 0.6.0's Python `LlmSpec` also exposes `provider: generic` with
`provider_id`, `alias`, `model_id`, optional `options`, and `api_key_env` for
compiled generation providers. The resolver forwards that SDK contract. A
catalog generation entry alone still does not select it for `Agent.answer`.

## Integration with Research Guild

Use the [research blueprint](../showcase/apps/uniko_research_guild.json) and
`UnikoResearchCoordinator`. Search and scrape results return to the coordinator;
successfully enumerated files become typed `IngestDocumentRequest` messages
with external-evidence provenance. The coordinator waits for every ingestion
outcome before requesting scoped recall and dispatching the exact returned
bundle to the synthesis LLM agent. User and assistant writes are acknowledged,
and finalization precedes the single final response.

## Payload Models

All request/response models are Pydantic BaseModels:

### ObserveTurnRequest
- `session_id`: Optional session ID
- `sender_id`: Participant ID
- `content`: Message text
- `message_id`: Optional unique ID
- `metadata`: Optional key-value pairs
- `attachments`: Optional attachment specs

### RecallRequest
- `query`: Search query
- `token_budget`: Optional native token budget (1–10000)
- `min_score`, `reranker`, `reference_ts`: Optional native recall overrides
- `scope`: Required; `sessions=null` searches the private store without session filtering
- `allowed_record_kinds`: Required, including `unknown` only when explicitly desired
- `item_limit`, `max_characters`: Hard response bounds

### AnswerRequest
- `question`: Question to answer
- `max_tokens`: Unsupported in Uniko 0.6.0; non-null values are rejected. Set generation limits on the Guild synthesis LLM agent.
- `scope`: Optional recall scope

### Error Handling

Errors return `MemoryAgentError`:
```python
{
    "error": "llm_not_configured",
    "message": "Memory answer generation is unavailable."
}
```

## Testing

```bash
# Run all tests
poetry run pytest

# Run specific test file
poetry run pytest tests/test_memory_agent.py

# With coverage
poetry run pytest --cov=rustic_ai.uniko_agent
```

## Architecture

### Private Agent Memory

- One private `uniko.Uniko` store per organization, guild, and agent
- Persistent storage is resolved from the injected agent filesystem, never cwd
- Other agents share memory through typed requests to MemoryAgent
- Incoming documents are read from the separate guild-scoped filesystem

### Dependency Injection

```
GuildSpec
  └─ dependency_map["uniko"] = UnikoResolver  (agent-scoped)
       └─ resolve(org_id, guild_id, agent_id) → lifecycle-managed native Agent handle
            └─ Injects dependency_map["filesystem"] at agent scope for storage
```

### Message Flow

```
User/Agent
  └─ ObserveTurnRequest → MemoryAgent
       └─ uniko_agent.session().observe(turn)
       └─ ObserveResult (extracted entities, observations)

User/Agent
  └─ RecallRequest → MemoryAgent
       └─ uniko_agent.recall_with(query, scope, supported overrides)
       └─ RecallResponse (ranked items with provenance)
```

## Core integration contracts

`IngestDocumentRequest` preserves `record_id`, `session_id` and `media_link`.
Alternatively supply `source=MemorySource(text=..., mime_type="text/markdown")`
or `MemorySource(base64_data=..., mime_type=...)`. Choose exactly one source.
Attachments use the same source model. MIME types and path hints reach native
extractors. Limits apply before writes, including bounded sync/async filesystem
reads. Host paths and remote URLs are rejected as ingestion sources.

New writes carry native category, logical `source_id` and store-unique
`revision_id`. Visibility is supported on turns; Uniko 0.6.0 does not expose
visibility on document inputs, so explicit document visibility is rejected.
Record kinds remain assigned by authorized producers. Unknown classification
is a read-only result kind. The legacy envelope/prefix reader remains available
through a bounded compatibility pass and reports missing native metadata.
Native categories and sources filter candidates before ranking. Existing
records cannot acquire missing logical-source or revision metadata on read.

`IngestOutcome` reports native artifact/chunk/page/block identities,
deduplication and extraction errors. `stored` and `searchable` are separate:
retained bytes or an empty PDF do not imply evidence was extracted. Streaming
batches use durable per-item observations and emit correlated `BatchItemOutcome` messages and one terminal
`BatchSubmitResponse`; failed items do not undo earlier accepted items.
Direct instances reject streaming submit/flush controls before writes.

`RecallItem` preserves native sources, category, source/revision identity,
context, address and token count. Intact native text retains its native count;
stripped legacy envelopes and truncated text use `cl100k_base`. Cache the
Python tiktoken encoding during deployment for offline token-bounded retrieval.
Precedence is explicit request overrides, explicit legacy agent overrides,
then native effective settings. Unset legacy token fields are `None`, allowing
config serialization to preserve this precedence.

`SourceSearchRequest` and `SourceReadRequest` expose lexical search, outline,
addressed text and available original artifact bytes. Reads apply scope allow
predicates before dereferencing and return `available=false` for absent or
unauthorized sources. Limits bound source responses. `scope_producers` can
restrict scope selection to trusted Guild agents; `viewer_producers` accepts
viewer membership only from trusted routing context, never unchecked requests.

`EffectiveConfigRequest`, `CapabilityRequest` and `MemoryHealthRequest` return
`MemoryDiagnostics`, separating configured values, observed SDK information
and Unknown readiness/provider capabilities. They never imply OCR, multimodal,
BGE-M3 or hardware acceleration merely because configuration was accepted.
Deployment catalog/schema/rule files require readable absolute local paths and
are validated before persistent store opening. The resolver uses
`readiness_policy="sdk_default"` (native best-effort warmup); requesting
`require_verified` remains unavailable in this integration. The native SDK now
provides readiness APIs, but this release does not expose their policy contract.
Native storage compatibility
checks remain authoritative; incompatible stores require explicit migration.

The [research blueprint](../showcase/apps/uniko_research_guild.json) uses a Guild
coordinator to preserve authenticated user identity and stable request IDs,
enumerate successful scrape outputs, wait for per-document ingestion outcomes,
and ignore duplicate/late results. Recall sufficiency remains `score > 0.05`.
The existing synthesis LLM agent receives the original question and the exact
returned bounded context, including attribution. Its `max_tokens` controls
answer length. MemoryAgent does not own Guild prompt orchestration. Native
`AnswerRequest` remains supported for configured SDK-native generation and
returns its complete generation context and citations.

Resolver handles track accepted native operations. `shutdown()` stops new
work, drains accepted work, clears cached handles and shuts down the instance;
use `await shutdown_async()` from an event loop with active work. Cleanup is
idempotent and failures from externally retained raw native handles remain
visible. Synchronization is bounded per agent and independent of session count
or event-loop lifetime. The LLM memory wrapper retains native atomic user/
assistant commits and finalization under the same lifecycle reservation.

## Later release gates

BGE-M3 dense/sparse/ColBERT certification, scanned-PDF OCR and
multimodal adapters remain separate milestones in the completion plan.

## Future Enhancements (Phase 3+)

Planned features:

- **BGE-M3 retrieval certification** across dense, sparse and ColBERT paths
- **Scanned-PDF OCR and multimodal workflows** with extraction evidence
- **Operational-scale and accelerated deployment validation**

Native rule inspection, procedure matching/feedback, and structured goals/tasks
are already exposed; arbitrary graph/Locy mutation is not part of this memory contract.

## References

- [Uniko Documentation](https://uniko.ai/docs)
- [Rustic AI Core](https://github.com/dragonscale-ai/rustic-ai)
- [Uniko GitHub](https://github.com/rustic-ai/uniko)

## License

Apache 2.0 - see LICENSE file

### Machine-readable configuration and examples

The package includes [native configuration schema](src/rustic_ai/uniko_agent/schemas/uniko-config.schema.json),
[request schemas](src/rustic_ai/uniko_agent/schemas/memory-requests.schema.json),
[agent policy schema](src/rustic_ai/uniko_agent/schemas/memory-agent-config.schema.json),
[resolver schema](src/rustic_ai/uniko_agent/schemas/resolver.schema.json),
and a [G1 configuration/ingestion/recall example](examples/g1-contracts.json).
Native section overrides retain SDK whole-section replacement semantics.
Schema validation describes accepted settings; `MemoryDiagnostics.unknown`
records stages/providers whose availability cannot be verified by the SDK.


## Structured experience (G2)

Typed messages expose native tool calls, actions, episodes, observations and facts.
`RecordToolCallRequest` accepts arguments, one text/JSON/byte output, status,
error, timing, message trigger and prior-call references. `output_kind: json`
preserves an explicit JSON null through serialization. Turn `tool_calls` use the
same contract. `RecordActionRequest` and `RecordEpisodeRequest` preserve native
causal edges. Outputs stay bounded; tool failures are retained as data.

`AddObservationRequest` anchors a claim to an authorized message and returns its
actual observation ID. `AssertFactRequest` validates supporting observation IDs;
`InvalidateFactRequest` validates the fact and optional replacement. These
operations require explicit dimensional scope. Native scope support varies by
record type; a dimension that cannot authorize a record fails closed.

`CommitMemoryUnitRequest` commits all turns, attachments and embedded tool calls
through `Session.commit_unit`. It prepares inputs before dispatch, with at most
128 turns, 32 aggregate attachments and 32 MiB of prepared data by default.
The existing streaming batch retains per-item success and failure outcomes;
items containing tool calls use individual atomic units and receipts. An uncertain
item retains its message ID, operation and operation ID with `stored: null`,
while cancelled items that never started use `stored: false`. The summary counts
known stored items in `submitted_count` and uncertain items in `uncertain_count`.

`MatchProceduresRequest` exposes native learned procedures in the private store.
`RecordProcedureUseRequest` records success/failure feedback.
`ListMemoryRulesRequest`, `ExplainMemoryRuleRequest` and `ReadExperienceRequest`
provide bounded reads without arbitrary graph mutation. Store-wide consolidation,
fact invalidation and procedure feedback require a sender explicitly listed in
`control_producers`; the default list is empty. Consolidation is deterministic
and does not enable optional LLM consolidation.

Structured ownership comes from the authenticated reporting message sender,
not a caller-provided agent identity. Goal/task reads default to that owner;
selecting another or legacy owner requires `scope_producers` authorization.
Records are not migrated. Uniko 0.6.0 native agent registration idempotently creates the reporting actor
before adding membership in the resolver's trusted organization. No synthetic
messages or actions are created to bootstrap it.

Each structured mutation accepts `operation_id`. When omitted, object creation
uses a supplied object ID or the message ID; missing object IDs are generated
from the reporting actor and operation identity. Receipts live beside the private
native store in `.rustic-operations.sqlite3` (in-memory stores use an in-memory
journal). Keep the journal with the store during backup and restore. A completed
receipt replays its compact response; goal/task creation returns the current
native view after later transitions. A changed payload conflicts. Existing
native IDs without a matching receipt are rejected rather than merged again.

A command is durably claimed before its native effect and completed before its
reply is published. Native graph writes and SQLite cannot commit atomically.
If journal completion and uncertainty persistence both fail, the pending claim
still prevents redispatch and the original cancellation or error is preserved.
A crash, cancellation or ambiguous failure after dispatch yields
`operation_outcome_unknown`, and retrying cannot repeat the effect.
`MemoryOperationStatusRequest` reports the actor's receipt state. Resolving an
unknown effect requires inspecting the native store; there is no automatic
retry or receipt-reset API. Receipt retention follows the private store lifecycle.


Uniko 0.6.0 attributes embedded tool calls to their turn sender. Until
[U68](https://github.com/rustic-ai/uniko/issues/68) adds an independent performer
override, turns containing tools must use the authenticated reporting agent as
`sender_id`. A unit can include a separate user turn and a reporting-agent turn
whose tool call references that user's message with `triggered_by`. Standalone
`RecordToolCallRequest` can also reference a user's previously stored message.
Mismatched embedded-tool senders are rejected before any native write; user
message attribution is never rewritten to satisfy tool ownership.
