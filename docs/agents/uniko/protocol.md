# Uniko memory protocols

Core formats live in `rustic_ai.uniko_agent.models`; structured experience formats live in `rustic_ai.uniko_agent.structured_models`. Both sets are exported from `rustic_ai.uniko_agent`. Use their defining module's fully qualified format in JSON routes.

Unlike [Uni-DB's protocol](../unidb/protocol.md), these models do not all carry a common protocol-version/request-ID envelope. Guild message context supplies workflow correlation. Preserve the exact request/session context through routes; do not invent fields absent from the selected model.

## Core memory

| Request/input | Response | Purpose |
| --- | --- | --- |
| `ObserveTurnRequest` | `ObserveResult` | Direct turn observation, extraction, typed attachments and embedded tool calls |
| `RecordMemoryRequest` | `RecordMemoryResult` | Stable producer-assigned record ID and kind |
| `ChatCompletionRequest`, `ChatCompletionResponse` | No success payload; errors use `MemoryAgentError` | Conversation recording/finalization from configured trusted producers |
| `IngestDocumentRequest` | `IngestOutcome` | Inline/base64/shared-filesystem source ingestion |
| `BatchSubmitRequest` | `BatchItemOutcome`, then `BatchSubmitResponse` | Streaming-only per-item outcomes and terminal summary |
| `RecallRequest`, `RecallUserSessionsRequest` | `RecallResponse` | Bounded, attributed memory retrieval |
| `AnswerRequest` | `AnswerResponse` | SDK-native generation using configured `llm_spec`, context and citations |
| `FinalizeMemorySessionRequest` | `FinalizeMemorySessionResult` | Build finalized session memory |
| `ForgetMemoryRecordRequest`, `DeleteMemorySessionRequest`, `ForgetMemoryParticipantRequest` | `MemoryDeletionResult` | Typed redaction/deletion counts |
| `SourceSearchRequest`, `SourceReadRequest` | `SourceResponse` | Lexical source search, outline, addressed text or available original bytes |
| `EffectiveConfigRequest`, `CapabilityRequest`, `MemoryHealthRequest` | `MemoryDiagnostics` | Configured values, observed information, explicit unknowns |

Direct observation does not need a streaming flush. Direct instances reject batch submit/flush controls before writing. A batch is not one transaction: known stored items, rejected items, and uncertain items remain distinct. The terminal summary exposes `submitted_count`, `uncertain_count`, `outcomes`, `flushed`, and errors.

`IngestOutcome` preserves artifact, chunk, page/block, deduplication, and extraction information. `stored: true` does not imply `searchable: true`. Choose exactly one `MemorySource` representation: `text`, `base64_data`, or a `media_link` with `on_filesystem: true`. Uniko does not fetch remote URLs through this protocol.

## Recall scope and bounds

`RecallRequest` requires both `MemoryScope` and nonempty `allowed_record_kinds`. Scope supports sessions, participants, time range, categories, sources, superseded revisions, and trusted viewer membership. Set `sessions=[...]` for explicit sessions or `sessions=None` for no session filter within this agent's private store. An empty sessions list is invalid.

The agent checks configured `scope_producers`. Viewer membership must match trusted `memory_viewer` context from a sender allowed by `viewer_producers`. A field containing a claimed user/team identity is not authentication. Source/experience reads apply supported native scope and ownership checks before dereferencing; unavailable or unauthorized records return unavailable outcomes where supported.

| Recall control | Default / behavior |
| --- | --- |
| `item_limit` | 10; maximum 50 |
| `max_characters` | 6,000; maximum 32,000 |
| `token_budget` | Explicit request, then explicit legacy agent override, then native effective config |
| `min_score` | Optional native override in [0,1] |
| `reranker` | Optional per-request native override |
| `reference_ts` | Optional native reference time |

Results retain record kind separately from native memory item kind, plus native source/revision/category information, context, source addresses, and token counts. A bounded legacy compatibility pass cannot reconstruct missing provenance. Legacy records cannot satisfy filters that require absent native metadata. Truncation is explicit; legacy or truncated text is counted with cached `cl100k_base` tokenization.

## Structured experience

| Request | Response | Purpose |
| --- | --- | --- |
| `RecordToolCallRequest` | `ToolCallResponse` | Arguments, one output representation, status/error, timing, causal references |
| `RecordActionRequest` | `ActionResponse` | Native action and causal links |
| `RecordEpisodeRequest` | `EpisodeResponse` | Episode outcome/state/delta and involved actions |
| `AddObservationRequest` | `ObservationResponse` | Claim anchored to an authorized message |
| `AssertFactRequest` | `FactResponse` | Supported fact with validated observation identities |
| `InvalidateFactRequest` | `FactInvalidationResponse` | Invalidate/replace an authorized fact; control sender required |
| `CommitMemoryUnitRequest` | `MemoryUnitResponse` | Atomic turns, attachments, and embedded tool calls in one session |
| `ConsolidateMemoryRequest` | `ConsolidationResponse` | Deterministic consolidation; control sender required |
| `CreateGoalRequest`, `UpdateGoalRequest`, `GetGoalsRequest` | `GoalView`, `GoalStatusResponse`, `GoalsListResponse` | Owned goals, native transitions, listing |
| `CreateTaskRequest`, `UpdateTaskRequest` | `TaskView`, `TaskStatusResponse` | Owned tasks, native transitions/dependencies |
| `GoalContextRequest` | `GoalContext` | Tasks, sessions, recent messages, facts, entities |
| `MatchProceduresRequest`, `RecordProcedureUseRequest` | `ProceduresResponse`, `ProcedureUseResponse` | Learned procedure matching and controlled feedback |
| `ListMemoryRulesRequest`, `ExplainMemoryRuleRequest` | `MemoryRulesResponse` | Native rule definitions/explanations |
| `ReadExperienceRequest` | `ExperienceResponse` | Bounded authorized action/episode/observation/fact/goal/task read |
| `MemoryOperationStatusRequest` | `MemoryOperationStatus` | Reconcile a structured operation identity |

Structured ownership comes from the reporting transport sender. Alternate/legacy ownership requires scope-producer authorization. Native registration uses the resolver's organization membership; in 0.5.1 the participant kind remains unknown. Embedded tool-call performer ownership remains with that turn's participant.

Goal/task identities are native IDs, not reconstructed node IDs. Task priority accepts exclusive legacy `priority` (1–5) or `native_priority` (0–1); responses return a native float. Goal context explicitly reports `episodes_available: false` in 0.5.1. Unsupported controls fail rather than being silently ignored.

## Replay and failure behavior

Structured mutations accept `operation_id`. When omitted, creation uses a supplied object identity or transport message identity. Generated IDs derive from the reporting actor and operation identity. Use explicit stable operation IDs when retrying after uncertain delivery.

The receipt journal is `.rustic-operations.sqlite3` beside the persistent native store; in-memory stores use an in-memory journal. Completed replay returns the compact recorded response; replayed goal/task creation can return the current native view after later transitions. Changed-payload reuse conflicts. Existing native IDs without a matching receipt are rejected instead of being silently merged.

The journal and native mutation are separate commit boundaries. A crash after dispatch or receipt failure can produce `operation_outcome_unknown`; unresolved work is not automatically reexecuted. Reconcile with `MemoryOperationStatusRequest`, whose states are `not_found`, `completed`, or `outcome_unknown`.

Failures use `ctx.send_error(MemoryAgentError(error, message, details))`. Structured failures can include operation and identity details. Batch uncertainty preserves operation/message identities and `stored: null`; unstarted cancelled items report `stored: false`. Error-topic consumers and guild routes decide recovery or workflow termination. Do not equate one native operation with final user-task completion.

## Agent resource limits

| Config field | Default |
| --- | --- |
| `max_source_bytes` | 16 MiB |
| `max_attachments` | 32 |
| `max_batch_items` | 128 |
| `max_unit_bytes` | 32 MiB |
| `max_structured_output_bytes` | 16 MiB |
| `legacy_recall_limit` | 50 |

A memory unit allows up to 128 turns and 32 aggregate attachments, all in its session. Inputs are prepared/bounded before native unit dispatch. `recall_max_tokens` defaults to `None`, preserving native configuration precedence. `recall_phase1_only=True` and a non-null `answer_max_tokens` are rejected: configure generation limits on the synthesis LLM agent.

Read the [agent guide](index.md), [resolver guide](../../dependencies/uniko/index.md), and [implementation/acceptance plan](../../design/uniko-agent-completion.md) for composition and current release gates.
