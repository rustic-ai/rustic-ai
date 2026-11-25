# Uniko agent implementation and completion plan

This plan tracks completion of Rustic's Uniko memory integration: reliable configuration, ingestion, extraction, retrieval, lifecycle and observable failure handling. Completion is measured by supported user workflows and executable acceptance tests. Configuration acceptance and a successful API response alone do not establish that a requested inference stage ran.

The core text and document integration can progress independently of the upstream feature requests. OCR, multimodal processing and larger deployments have separate release gates and explicit dependencies.

The current usage documentation is the [agent guide](../agents/uniko/index.md), [message protocol](../agents/uniko/protocol.md), and [resolver guide](../dependencies/uniko/index.md). The implementation evidence below retains its recorded dates and platforms.

## Baseline and tracking rules

| Item | Status and evidence |
| --- | --- |
| Updated | 2026-11-17 |
| Current implementation | [`b21e144`](https://github.com/milliondreams/rustic-ai/commit/b21e144), signed and pushed to the milliondreams fork's `main` branch |
| Initial code baseline | `7bc3cf0`; historical source links below retain this pre-implementation snapshot |
| Change under review | [Rustic PR 480](https://github.com/rustic-ai/rustic-ai/pull/480); dependency baseline merged through [PR 479](https://github.com/rustic-ai/rustic-ai/pull/479) |
| Native dependency | Uniko `>=0.5.1,<0.6.0`; locks currently select 0.5.1 |
| Runtime environment validated | Python 3.13.12, macOS ARM64, CPU Uniko wheel |
| Upstream source snapshots checked | Uniko `28f8a1ae3e343f62392800b7d693c0bac45c7c80`; uni-xervo `fd312158599cb3fe429e93c56f07f7124d216642` |
| Last full local CI | 2026-11-17: 2,020 passed, 88 skipped, 3 xfailed, 2 xpassed; exit 0; Redis and NATS/JetStream enabled |
| Latest review regressions | Eight new cases passed; all 18 G2 cases passed in full local CI, including routed native priority |
| Earlier regression baseline | G1: 2,002 passed, 88 skipped, 3 xfailed, 2 xpassed; focused integration: 113 passed, 2 skipped; both exit 0 |
| Other current checks | Formatting, lint, mypy (701 files), strict docs and Uniko source/wheel build passed; five packaged schemas match sources; all 25 lockfiles fresh |

The current results validate G1/G2 and the four selected review fixes. Earlier results remain recorded as a regression baseline. They do not close the OCR, BGE-M3, richer retrieval or multimodal gates below. Existing xfails/xpasses and skipped tests must be reviewed for relevance to each release claim.

Task states are **Open**, **In progress**, **Waiting on upstream**, **Verified**, and **Deferred**. P0 means current contract correctness; P1 means required core functionality; P2 means an extended capability or scale improvement. A task becomes Verified only when its acceptance evidence is linked. A deferred feature must disappear from supported-feature claims or have an explicit unavailable result.

Each task record should include an assignee, implementation PR/commit, test command and result, dependency versions, platform/model profile, and any relevant upstream issue. Assignees remain unassigned until work is taken.

## Scope and completion gates

The scope includes `MemoryAgent`, `UnikoResolver`, `UnikoMemoriesStore`, `MemoryRequestInitializerAgent`, their public models, and their research/analyst Guild integrations. It does not require implementing every uni-xervo task or exposing internal graph mutation APIs without a use case.

| Gate | User outcome | Current state | Required tasks |
| --- | --- | --- | --- |
| G1 Core memory | Text and supported documents can be recorded, recalled, attributed and deleted across restart with user isolation | Verified | C01–C08, I01–I05, R01–R06, L01–L04, T01–T03 |
| G2 Structured experience | Tools, actions, facts and goals use native relationships and stable identities | Verified | I06–I08, R07, L05, T04 |
| G3 Hybrid retrieval | A BGE-M3 store demonstrably uses dense, sparse and ColBERT paths with correct persistence | Open | C07, R08, T05 |
| G4 OCR documents | Scanned PDFs become searchable, traceable text with explicit extraction outcomes | Open | M01, M04, T06 |
| G5 Multimodal memory | Advertised image/audio/video workflows preserve original media and searchable derivations | Open | M02–M05, T07 |
| G6 Operational scale | Resource sharing, readiness, bounded queues and recovery satisfy the intended deployment | Open | C05–C06, L03–L04, L06, T08 |

G1 and G2 are implemented and locally verified with the evidence and runtime boundaries below. G2 review fixes are signed and pushed in `b21e144`; PR 480 remains the integration review. G3 builds on their identity, provenance and retrieval contracts. G4/G5 may use external extraction adapters while upstream packaging and adapters evolve. G6 needs a measured deployment budget; no arbitrary concurrency target is assumed.

## Current delivery and review status

G1 and G2 are **Verified locally**. Implementation is on the fork's `main` branch
and submitted through [PR 480](https://github.com/rustic-ai/rustic-ai/pull/480).
This records local acceptance; upstream review and merge remain pending.
G3–G6 are **Open** and require their own implementation and acceptance evidence.

| Delivery | Status | Implementation |
| --- | --- | --- |
| G1 core memory | Verified locally; submitted for upstream review | [`38416ab`](https://github.com/milliondreams/rustic-ai/commit/38416ab) |
| G2 structured experience | Verified locally; submitted for upstream review | [`b67a534`](https://github.com/milliondreams/rustic-ai/commit/b67a534) |
| Selected G2 review fixes | All four addressed and verified locally; signed and pushed | [`b21e144`](https://github.com/milliondreams/rustic-ai/commit/b21e144) |

| Selected finding | Status | Result and acceptance evidence |
| --- | --- | --- |
| Native priority fails after serialization | Verified | Native and legacy priority choices survive JSON round trips, including native zero. A real Guild-routed task returns native priority `0.7`. |
| Goal listing bypasses exact ownership | Verified | Both all-goal and active-goal listing exclude native records with conflicting owners before serializing their views or counting them. Legitimately owned goals remain visible. |
| Batch cancellation hides uncertain effects | Verified | Cancellation after native Message/Action writes preserves `operation_outcome_unknown`, `stored: null`, stable message/operation IDs and `uncertain_count`. Unstarted items report `cancelled` with `stored: false`; replay does not duplicate the native action. |
| Journal failure suppresses terminal error | Verified | Simultaneous receipt completion and uncertainty-update I/O failures still emit one typed unknown-outcome response with its operation identity. Original cancellation survives, the operation gate releases and the pending claim prevents redispatch. |

Regression evidence is in
[test_g2_structured.py](https://github.com/milliondreams/rustic-ai/blob/b21e144/uniko-agent/tests/test_g2_structured.py)
and [test_g2_routed.py](https://github.com/milliondreams/rustic-ai/blob/b21e144/uniko-agent/tests/test_g2_routed.py).
All four fixes and the regenerated request schema are included in PR 480.
The full local run used `tox -e test -- --workers 4` on Python 3.13.12/macOS ARM64
with Redis and NATS/JetStream: **2,020 passed, 88 skipped, 3 xfailed, 2 xpassed**.
Configured expensive/provider tests remain excluded; this does not establish
Windows, Linux, OCR, BGE-M3 or multimodal acceptance.

Remaining work is G3 hybrid retrieval, G4 OCR, G5 multimodal memory and G6
operational scale. G2 retains its documented registration and embedded-tool
performer boundaries tracked by [Uniko #67](https://github.com/rustic-ai/uniko/issues/67)
and [Uniko #68](https://github.com/rustic-ai/uniko/issues/68).

## Ownership and message flow

| Component | Responsibility |
| --- | --- |
| Guild routes and initializer | Carry authenticated user identity and request correlation; route typed requests and authoritative completion events |
| MemoryAgent | Validate domain requests, authorize scope, translate to native calls, return bounded results and terminal outcomes |
| UnikoMemoriesStore | Recall bounded conversational context and atomically record user/assistant pairs for LLM-agent use |
| UnikoResolver | Resolve private storage, configure native builders, manage resource ownership and expose runtime capability/readiness |
| Extraction dependencies | Turn media into explicit derivations; manage provider credentials and media processing outside routing expressions |
| Uniko | Own graph, sources, memory semantics, native extraction, consolidation and recall |
| uni-xervo | Own model/task/provider configuration, loading and inference |

Other Rustic agents access a memory agent's store through messages. They do not acquire a shared guild database merely because a native handle uses the guild ID. Sharing model resources must preserve separate graph stores and access scopes.

```text
User Proxy
  -- ChatCompletionRequest --> MemoryRequestInitializerAgent
  -- initialized ChatCompletionRequest --> research or analyst workflow

Workflow
  -- RecordMemoryRequest / ObserveTurnRequest / IngestDocumentRequest --> MemoryAgent
MemoryAgent
  -- RecordMemoryResult / ObserveResult / IngestOutcome or MemoryAgentError --> workflow
Workflow
  -- all expected ingestion outcomes + source enumeration completion --> ingestion barrier
  -- RecallRequest using the original resolved lookup --> MemoryAgent
MemoryAgent
  -- RecallResponse or MemoryAgentError --> synthesis stage
Synthesis
  -- ChatCompletionResponse --> User Proxy
  -- final visible response recording --> memory workflow
```

Each accepted operation has one terminal outcome correlated with its request. Bulk ingestion additionally has one terminal outcome per item and a batch completion result. Partial success, zero usable sources, irrelevant sources and provider failure remain distinguishable. Late results cannot restart a completed workflow or add extra user responses.

## Historical baseline and defects

At the initial baseline, the agent had 19 processors covering conversation recording, typed records, session finalization/deletion, participant forgetting, observation, recall, answers, document ingestion, streaming batches and basic goals/tasks. The resolver accepted native model/configuration inputs, and the separate memory wrapper used native atomic commits for user/assistant pairs.

| Defect | Impact | Task |
| --- | --- | --- |
| Nonempty observation attachments call an undefined `_build_ingest_source` | Advertised attachments fail before observation | I01 |
| Auto-flush defaults to true while resolver streaming defaults to false | An observation can commit and then produce an error from flush | L01 |
| Unmarked native recall items are discarded | Ordinary observations or externally populated native records can be invisible | R01 |
| `sessions=None` becomes process-local session-lock keys | Older persisted sessions may be excluded from unrestricted recall | R02 |
| Record forgetting treats conversation-turn records as documents | An observed turn can remain stored after the wrong deletion path | L02 |
| Generated goal/task IDs are reconstructed from node IDs | Returned identifiers may not address the created native object | L05 |
| Agent recall/answer limits are declared but unused | Caller expectations differ from native execution | C01 |
| Source/result serializers omit supported native metadata | Provenance, addressed retrieval and diagnostics are incomplete | I05, R05 |

This table records the pre-G1 findings. G1 resolves the attachment, direct-observe flush, unrestricted session scope, conversation deletion, provenance and recall-control findings. G2 resolves the generated goal/task ID finding through L05 with native identity and restart regressions.

## G1 implementation and acceptance evidence

G1 uses Uniko 0.5.1 on Python 3.13/macOS ARM64 with the CPU wheel. The native model/config/catalog surface remains the configuration authority. Request overrides take precedence over explicitly configured legacy recall limits, then effective native defaults. Unsupported phase-one and answer-generation controls fail explicitly. Schemas and a runnable payload example are published in [the package](https://github.com/milliondreams/rustic-ai/blob/main/uniko-agent/README.md#machine-readable-configuration-and-examples).

The implemented ingestion boundary accepts inline text, base64 bytes or an injected guild-filesystem MediaLink. Reads are capped at 16 MiB per source, observations at 32 attachments and batches at 128 items. Text, Markdown, HTML, CSV, JSON, code and native-text PDFs use native extraction. Outcomes separate stored bytes from searchable text, preserve native IDs/deduplication/extraction errors, and retain category/source/revision and attachment relationships. Reserved provenance categories cannot override producer-assigned kinds. Native document visibility is unavailable and rejected rather than implied.

Recall preserves native provenance and marks unclassified records Unknown. Native dimensional filters run before ranking; a separate bounded compatibility pass supports existing Rustic records and explicitly reports its metadata limitations. Returned item, character and token budgets are enforced; counts use native values where intact and labelled cl100k_base counts where rendered or truncated. Source search/read/outline/original operations apply session and available dimensional scope, viewer authorization and superseded-revision policy. A stored artifact without extracted chunks remains readable through its authorized session anchor.

The research coordinator owns correlated branch enumeration, document ingestion barriers and exactly one final result. It keeps per-user sessions, rejects untrusted result senders and ignores duplicates/late results. It passes the original question and the exact attributed RecallResponse JSON to the existing synthesis LLMAgent. That agent's max_tokens configuration controls generation. MemoryAgent retains the native AnswerRequest/AnswerResponse compatibility path with the complete generation context; unsupported generation controls are rejected.

Resolver-owned handles drain accepted operations before releasing native children and shutting down. Initialization and shutdown are synchronized; new work is rejected after closing begins. The per-agent operation gate is bounded independently of session count and event-loop lifetime. Direct observations never flush a disabled streaming pipeline, batches report durable per-item outcomes plus one terminal batch outcome, and the LLM memory wrapper retains atomic user/assistant commits.

| Evidence | Executable coverage |
| --- | --- |
| C01–C04, I01–I05, R01–R05, L01–L04 | [G1 native and boundary regressions](https://github.com/milliondreams/rustic-ai/blob/main/uniko-agent/tests/test_g1_contracts.py), [memory contracts](https://github.com/milliondreams/rustic-ai/blob/main/uniko-agent/tests/test_memory_writer_reader_contract.py), [native integration](https://github.com/milliondreams/rustic-ai/blob/main/uniko-agent/tests/test_uniko_native_integration.py) |
| C05–C08 | [Diagnostics/deployment tests](https://github.com/milliondreams/rustic-ai/blob/main/uniko-agent/tests/test_g1_contracts.py), [resolver configuration tests](https://github.com/milliondreams/rustic-ai/blob/main/uniko-agent/tests/test_uniko_integration.py), [deployment/runtime documentation](https://github.com/milliondreams/rustic-ai/blob/main/uniko-agent/README.md) |
| T01, T02 and R02 | [Private-store restart/isolation](https://github.com/milliondreams/rustic-ai/blob/main/uniko-agent/tests/test_private_filesystem_storage.py), [scoped document recall](https://github.com/milliondreams/rustic-ai/blob/main/uniko-agent/tests/test_document_recall_scope.py), [routed sessions](https://github.com/milliondreams/rustic-ai/blob/main/uniko-agent/tests/test_routed_conversation_sessions.py), [atomic memory wrapper](https://github.com/milliondreams/rustic-ai/blob/main/uniko-agent/tests/test_uniko_memories_store.py) |
| R06 and T03 | [Sequential research acceptance](https://github.com/milliondreams/rustic-ai/blob/main/showcase/tests/test_uniko_research_guild.py): real native ingestion/recall/finalization across document and remembered follow-up plus another user; controlled synthesis/search responses; partial/terminal failures, duplication and late-result tests |

Readiness remains Unknown where the SDK cannot expose it. sdk_default means native best-effort startup; require_verified is explicitly unavailable. Pipeline health and resource counts expose only observable SDK facts. Existing-store compatibility checks remain native; unsupported model/dimension changes require a fresh private store or a supported migration. Metal/CUDA, BGE-M3 channel population, OCR, multimodal adapters, native task IDs, model-backed extraction toggles and deployment-scale recovery are not certified by these CPU G1 checks. Those continue under G2–G6 and the upstream issues below.

Final local verification: full CI test task **2,002 passed, 88 skipped, 3 xfailed, 2 xpassed** (exit 0), followed by the final affected suite **113 passed, 2 skipped** (exit 0). Black/isort, flake8, mypy (696 source files), strict MkDocs, all 25 lock freshness checks, installed dependency consistency (361 packages) and four affected sdist/wheel builds pass. The Uniko wheel contains five validated schemas, including agent/resolver policies. Existing test-extra metadata references development-only dependencies and makes poetry check --lock report those declarations; the locks themselves are fresh and builds succeed. Credential-dependent/expensive tests remain skipped; live search/synthesis and other runtime platforms are not claimed.

Verified task states below apply to the bounded CPU G1 contract. Shared tasks C05–C07/L03–L04 remain subject to the additional G3/G6 model and deployment evidence; verified G1 diagnostics do not certify unavailable upstream capabilities.

## Configuration implementation

Keep engine settings in the resolver's native `config` surface and operation-specific settings in request models. Define one precedence rule and make it visible in effective configuration. Native validation remains authoritative; Rustic validates its own request relationships, capability requirements and deployment policy.

Preserve the established `alias: openai` input while documenting the native `provider` plus model-alias shape. Reject the removed embedded `mistralrs` input. Do not reinterpret it as the hosted Mistral API.

| ID | Priority | State | Implementation and acceptance |
| --- | --- | --- | --- |
| C01 | P0 | Verified | Resolve unused `recall_max_tokens`, `recall_phase1_only`, `answer_max_tokens` and `AnswerRequest.max_tokens`. Wire settings supported by native APIs; explicitly reject or retire unsupported controls. Demonstrate changed execution/output limits, rather than merely checking stored config. [G1 evidence](#g1-implementation-and-acceptance-evidence). |
| C02 | P1 | Verified | Publish schemas and examples for native sections and Rustic policy. Document that top-level model overrides replace a whole base-config section and merge partial values with native defaults. Test precedence, invalid combinations and unknown keys. [G1 evidence](#g1-implementation-and-acceptance-evidence). |
| C03 | P1 | Verified | Add typed source, extraction and recall request options; stop accepting undocumented dictionary fields that handlers silently ignore. Export and document the selected public models. [G1 evidence](#g1-implementation-and-acceptance-evidence). |
| C04 | P1 | Verified | Resolve catalog/schema/rule references using an explicit path policy. Validate readability and alias requirements before use; preserve the distinction between shared deployment configuration and private agent data. [G1 evidence](#g1-implementation-and-acceptance-evidence). |
| C05 | P1 | Verified | Expose effective config, compiled capability, model readiness and available diagnostics. Report Unknown when upstream cannot provide a fact. Never convert Unknown into Healthy. Track U56/U59/U60 and X61. [G1 evidence](#g1-implementation-and-acceptance-evidence). |
| C06 | P1 | Verified | Add an explicit readiness/prefetch policy and clear startup errors for unavailable required stages. Credential lookup belongs to dependencies. Parsing configuration must not require a live API call. [G1 evidence](#g1-implementation-and-acceptance-evidence). |
| C07 | P1 | Verified | Preflight existing store compatibility for model/dimension/hybrid changes. Reuse native checks and provide an explicit fresh-store or supported reindex workflow. Track U66. [G1 evidence](#g1-implementation-and-acceptance-evidence). |
| C08 | P1 | Verified | Update README, Guild examples, dependency profiles and package metadata to match supported runtime variants and settings. Install one CPU/Metal/CUDA distribution per environment; unsupported installation profiles must be explicit. [G1 evidence](#g1-implementation-and-acceptance-evidence). |

Minimum documented engine settings include embedding model/provider/dimensions/batching/prefixes/devices/options; vector algorithm/metric; chunk thresholds/size/overlap/context; NLP generation/precision/device; SRL and entity admission; observation rules; OCR; consolidation; recall weights/budget/thresholds; reranker; blob backend and source lifecycle.

## Ingestion and relation extraction implementation

| ID | Priority | State | Implementation and acceptance |
| --- | --- | --- | --- |
| I01 | P0 | Verified | Implement attachment translation through a typed source specification and injected filesystem boundaries. Test text, document and invalid attachments plus duplicate delivery. Preserve `ATTACHED_TO` relationships. [G1 evidence](#g1-implementation-and-acceptance-evidence). |
| I02 | P1 | Verified | Unify source conversion across observation, document requests and record ingestion. Honor requested MIME/content type, retain original source paths for native detection, and avoid overriding unknown MIME with octet-stream unnecessarily. [G1 evidence](#g1-implementation-and-acceptance-evidence). |
| I03 | P1 | Verified | Carry native category, logical source, revision and visibility fields in supported requests. Preserve producer-assigned record kind without inserting provenance prose into every embedding where native metadata can represent it. Test existing record compatibility. [G1 evidence](#g1-implementation-and-acceptance-evidence). |
| I04 | P1 | Verified | Add byte/attachment/item limits, bounded file reads or spooling, and complete typed bulk outcomes. Page and OCR processing budgets belong to G4. Decide inline text/bytes versus filesystem references explicitly. A failed item cannot deadlock an ingestion barrier. [G1 evidence](#g1-implementation-and-acceptance-evidence). |
| I05 | P1 | Verified | Return artifact identity, chunk IDs, deduplication, extraction outcome/error and available page/block references. An artifact stored without extracted text is not a searchable-success result. [G1 evidence](#g1-implementation-and-acceptance-evidence). |
| I06 | P1 | Verified | Add native tool-call/action/episode recording with stable IDs, arguments/output/status/timing and causal references. Avoid replacing these relationships with an executed-result text blob. Preserve bounded outputs and original tool failures. [G2 evidence](#g2-implementation-and-acceptance-evidence). |
| I07 | P1 | Verified | Expose appropriate explicit observation/fact assertion/invalidation and consolidation requests. Keep deterministic extraction as the default; optional LLM consolidation remains explicit and depends on U63. [G2 evidence](#g2-implementation-and-acceptance-evidence). |
| I08 | P1 | Verified | Expose atomic multi-turn units where needed. Typed batches must preserve selected timestamps, recipients, attachments and provenance; document that streamed submit has different session/context semantics. [G2 evidence](#g2-implementation-and-acceptance-evidence). |

Extraction acceptance must demonstrate SRL toggles, model generation/precision selection, custom observation-rule application, entity admission thresholds and code/document chunking on meaningful fixtures. Loading a rule file or selecting an NLP preset is insufficient. A missing model or invalid rule file must produce the selected failure/fallback outcome.

## Retrieval implementation

| ID | Priority | State | Implementation and acceptance |
| --- | --- | --- | --- |
| R01 | P0 | Verified | Replace envelope-dependent result exclusion with a native-provenance-aware contract. Mark Unknown explicitly when record classification is unavailable; apply producer/visibility policy without silently dropping valid authorized memories. Test ordinary turns, documents and derived facts. [G1 evidence](#g1-implementation-and-acceptance-evidence). |
| R02 | P0 | Verified | Preserve `sessions=None` as no session filter, independent of lock history. Locking must coordinate writes without changing the query domain. Reopen a store, touch one session, and retrieve an older untouched session. [G1 evidence](#g1-implementation-and-acceptance-evidence). |
| R03 | P1 | Verified | Map per-request native limits, token budget, minimum score, reranker override and historical reference timestamp through `recall_with`. Retain separate returned-item/character bounds. Use native token counts or explicitly label any display estimate. [G1 evidence](#g1-implementation-and-acceptance-evidence). |
| R04 | P1 | Verified | Expose time/category/source/revision and viewer scopes as typed fields. Apply available native filters before ranking; test rejected cross-user/team/org access and superseded-source behavior. Post-filtering alone cannot satisfy candidate-budget semantics. [G1 evidence](#g1-implementation-and-acceptance-evidence). |
| R05 | P1 | Verified | Preserve source session/tool/call IDs and item category/source/revision/context/address. Add source search, outline, bounded read and original artifact access contracts. Test the native addresses available for G1 documents and bounded line/byte reads. OCR page/block and media-segment certification belong to G4/G5. [G1 evidence](#g1-implementation-and-acceptance-evidence). |
| R06 | P1 | Verified | Make answer generation obey the same authorized retrieval policy as its returned context. Prefer bounded recall followed by Rustic LLM generation if native answer cannot enforce the contract. Do not filter the displayed context only after the LLM has consumed a broader bundle. [G1 evidence](#g1-implementation-and-acceptance-evidence). |
| R07 | P2 | Verified | Add procedure matching/success feedback and selected rule/query interfaces. Keep arbitrary graph mutation outside ordinary retrieval. Distinguish application authorization from native read/query capability. [G2 evidence](#g2-implementation-and-acceptance-evidence). |
| R08 | P1 | Open | Verify BGE-M3 dense, sparse and ColBERT indexing/query paths, including diagnostics and persistence. Track X60/X63; memory optimization is not a prerequisite for correctness testing. |

### BGE-M3 acceptance profile

This is a configuration candidate, not a declaration that the profile is release-ready:

```python
properties = {
    "embedding": "bge-m3",
    "reranker": {"enabled": True, "style": "colbert", "top_n": 50},
    "config": {"recall_sparse_enabled": True, "recall_limit": 15},
}
```

- Dense output is 1,024-dimensional. Learned sparse output uses a 250,002-token vocabulary. ColBERT output has 1,024 dimensions per token.
- The preset prepares hybrid columns on Chunk and Observation. Sparse recall and ColBERT reranking require their separate switches; selecting the preset does not enable both query paths.
- Inspect populated columns and confirm query-time contributions on fixtures selected to require the relevant recall phase. An early compact-phase answer need not run every channel.
- Prove that ColBERT changes eligible candidate order against a reference/tolerance and distinguish successful reranking from logged fallback.
- Test close/reopen, duplicate ingestion, sparse/ColBERT querying after reopen and mismatched configurations.
- Measure actual memory with the separate dense/hybrid instances. Do not assume X60 resource sharing exists.

## OCR and multimodal implementation

The currently audited Python wheel feature declarations do not enable Uniko's tiered `pdf-ocr` path. Accepting `config.ocr` is not an OCR capability guarantee. Image/audio/video callbacks are available in native Python, but Rustic does not register them, and native TextExtractor retains derived text rather than original media bytes.

| ID | Priority | State | Implementation and acceptance |
| --- | --- | --- | --- |
| M01 | P1 for G4 | Open | Implement a verified scanned-PDF path: upstream OCR-capable build/profile or an external extraction dependency. Preserve original PDF and derived page/block references. Identify native-text-only versus OCR output explicitly. Track U55. |
| M02 | P1 for G5 | Open | Register typed/configurable image OCR/caption and audio transcription adapters. Retain source bytes separately when native callbacks cannot. Test searchable text with regions or timestamps and source identity. Track U61. |
| M03 | P2 | Open | Define video sampling/transcription/caption composition with bounded duration/frame count and segment locations. Claim support only for the tested composition and providers. |
| M04 | P1 | Open | Expose extraction tier, model/revision, confidence when available, page/region/time address and retryable failure. Add an explicit re-extraction operation with revision/derivation identity; retries cannot silently duplicate sources. |
| M05 | P1 | Open | Decide text-derived recall versus native multimodal embedding/query support per profile. Until a real mixed-input index/query path exists, expose media-to-text retrieval accurately. Use direct ingestion while streaming lacks extractor parity; track U62. |

A multimodal source outcome must link original media, extracted text and location metadata. Test unreadable scans, empty captions, unsupported MIME, transcription failure and partially extracted multi-page documents. Preserve the distinction between stored bytes and usable searchable evidence.

## Identity, lifecycle and operations

| ID | Priority | State | Implementation and acceptance |
| --- | --- | --- | --- |
| L01 | P0 | Verified | Coordinate flush policy with streaming capability. Direct observation must not return failure solely because an unnecessary flush was attempted after commit. Explicit flush requests on unsupported instances return a clear error. [G1 evidence](#g1-implementation-and-acceptance-evidence). |
| L02 | P0 | Verified | Route turn/document forgetting by the actual stored record representation, including routed conversation turns. Coordinate deletion with writes/finalization. Test idempotent deletion, redacted/invalidation outcomes and recall after deletion. [G1 evidence](#g1-implementation-and-acceptance-evidence). |
| L03 | P1 | Verified | Make resolver lifecycle release cached Agent/Session handles before native shutdown. Bound session locks/cache growth, prevent new work during shutdown and prove queued work has an explicit terminal disposition. [G1 evidence](#g1-implementation-and-acceptance-evidence). |
| L04 | P1 | Verified | Expose pipeline health, queue/failure diagnostics, recovery policy and resource counts available upstream. Track U65 for dead-letter replay; unavailable replay must remain explicit. [G1 evidence](#g1-implementation-and-acceptance-evidence). |
| L05 | P0 | Verified | Assign stable external goal/task IDs before creation or consume an upstream creation view when U64 lands. Remove unsupported pause/resume claims and preserve native transition results rather than reporting unconditional success. [G2 evidence](#g2-implementation-and-acceptance-evidence). |
| L06 | P2 | Open | Measure multiple private stores, CPU/GPU capacity and concurrency; adopt shared runtime APIs when available. One store's shutdown cannot invalidate another store's inference or leak memory between users. Track U57/X60. |

Identity comes from authenticated transport context, not user-provided Cypher or untrusted memory. Every asynchronous branch carries request correlation. Stable record IDs and persisted source identities support retries and restart; process-local lock maps are not durable identity or retrieval scope.

## Public contract changes

G1 and G2 contracts below are implemented and exported; media retry remains proposed for later gates. Source outline and original access use the operation field on SourceReadRequest.

| Existing contract | Proposed work |
| --- | --- |
| ObserveTurnRequest | Typed attachment/source specification; native provenance/visibility; explicit flush policy |
| RecordMemoryRequest / IngestDocumentRequest | Consistent SourceSpec with identity/revision/category/MIME; bounded inputs; richer IngestOutcome |
| BatchSubmitRequest | Typed turn list and per-item terminal results; separate streaming versus atomic-unit operation |
| RecallRequest / MemoryScope | Native query controls and filters; explicit Unknown record-kind handling; stable addressed sources |
| AnswerRequest | Authorized bounded context shared with generation; supported generation controls only |
| No inspection requests | CapabilityRequest, EffectiveConfigRequest and MemoryHealthRequest or equivalent narrow APIs |
| No source navigation requests | SourceSearchRequest, SourceOutlineRequest and SourceReadRequest with bounded read options |
| Structured experience requests | RecordToolCallRequest, RecordActionRequest, RecordEpisodeRequest and selected fact/consolidation requests |
| No media retry request | ReextractSourceRequest with source/revision identity and extraction profile |

Use existing named memory topics for their established contracts; add dedicated control/source topics only when needed. Update producer and consumer routes together. Schema and route tests must prove each emitted format has a subscriber and one terminal result.

## Upstream dependencies

Issues were open when filed on 2026-11-16. Update status and selected release during implementation. These requests do not block fixing Rustic's own defects.

| Reference | Request | Integration decision |
| --- | --- | --- |
| [U55](https://github.com/rustic-ai/uniko/issues/55) | PDF OCR in Python wheels | Required for a native-wheel G4 claim; external extraction is a viable interim path |
| [U56](https://github.com/rustic-ai/uniko/issues/56) | Compiled capabilities/effective execution | Consume when available; report Unknown for missing introspection |
| [U57](https://github.com/rustic-ai/uniko/issues/57) | Shared runtimes/prefetch | Scale dependency after capacity measurements |
| [U58](https://github.com/rustic-ai/uniko/issues/58) | General generation providers/catalog alias | Use existing constructors or Rustic LLM generation until supported |
| [U59](https://github.com/rustic-ai/uniko/issues/59) | Degradation diagnostics | Needed for complete native-stage reporting; probes offer partial evidence |
| [U60](https://github.com/rustic-ai/uniko/issues/60) | Required-stage readiness | Opt-in readiness probes until native policy exists |
| [U61](https://github.com/rustic-ai/uniko/issues/61) | Model-backed structured media derivations | Build narrow extraction adapters and retain original media |
| [U62](https://github.com/rustic-ai/uniko/issues/62) | Streaming extractor mismatch, bug | Use direct media ingestion; reproduce with fixed-text callbacks |
| [U63](https://github.com/rustic-ai/uniko/issues/63) | Consolidation options/LLM refinement | Keep deterministic default; extended mode depends on SDK support |
| [U64](https://github.com/rustic-ai/uniko/issues/64) | Generated creation IDs/views | Assign IDs locally now; adopt upstream result later |
| [U65](https://github.com/rustic-ai/uniko/issues/65) | Dead-letter recovery | Do not imply retry scheduling is available |
| [U66](https://github.com/rustic-ai/uniko/issues/66) | Store compatibility/reindex | Reuse current checks; choose fresh stores for unsupported migrations |
| [U67](https://github.com/rustic-ai/uniko/issues/67) | Dedicated idempotent Python agent registration | Temporarily ensure real organization membership; report native participant kind as unknown |
| [U68](https://github.com/rustic-ai/uniko/issues/68) | Independent embedded-tool performer | Require a reporting-agent tool turn; separate user/reporter turns retain atomicity |
| [X60](https://github.com/rustic-ai/uni-xervo/issues/60) | BGE-M3 resource sharing | Optimization; measure current resource requirements |
| [X61](https://github.com/rustic-ai/uni-xervo/issues/61) | Runtime inspection | Supplies data for C05/L04 |
| [X62](https://github.com/rustic-ai/uni-xervo/issues/62) | Provider schemas | Consume authoritative schemas rather than duplicating option validation |
| [X63](https://github.com/rustic-ai/uni-xervo/issues/63) | Deployment acceptance matrix | Use as additional upstream evidence alongside Rustic tests |

The documented uni-db issue 130 is closed. Do not treat the Blackbook's older hybrid-reopen limitation as a current defect without reproduction against the pinned runtime. Similarly, sparse/multi-vector adapter issues already closed upstream are not open dependencies.

## Test and evidence matrix

| ID | State | Required evidence |
| --- | --- | --- |
| T01 | Verified | Native text/document lifecycle: record, duplicate replay, recall, finalize, close/reopen, forget and recall absence; verify source links and per-user/store isolation [G1 evidence](#g1-implementation-and-acceptance-evidence). |
| T02 | Verified | Committed regressions for attachment helper, flush-after-commit, null session scope, conversation deletion and unmarked recall records; generated goal/task IDs are covered by T04 in G2 [G1 evidence](#g1-implementation-and-acceptance-evidence). |
| T03 | Verified | Sequential Guild rounds: direct question, remembered follow-up, document-based follow-up, irrelevant document, partial failure and terminal failure; exactly one final response and no late mutation [G1 evidence](#g1-implementation-and-acceptance-evidence). |
| T04 | Verified | Native tool/action/episode/fact/goal relationships and atomic units; actual IDs survive restart and transitions reflect native success/failure [G2 evidence](#g2-implementation-and-acceptance-evidence). |
| T05 | Open | Real BGE-M3 vector population, sparse contribution, ColBERT ordering, persistence/reopen and memory measurement; mock-only runs cannot close G3 |
| T06 | Open | Scanned, native-text, mixed and malformed PDFs; searchable OCR text and page/block provenance on the selected supported build/profile |
| T07 | Open | Image/audio and selected video flows; original media retention, addressed derivations, extraction failure/retry, duplicate delivery and user scope |
| T08 | Open | Intended deployment's concurrent stores, bounded queue/backpressure, shutdown, restart, readiness and degraded provider handling on each claimed platform |

Extend existing tests in `uniko-agent/tests`, analyst memory integration tests and showcase route tests. Existing schema/configuration checks do not establish full live Guild behavior. Assert emitted format/topic/correlation/status and native side effects; avoid tests that merely mirror a builder call.

Representative commands from the repository root, using the locked development environment:

```bash
poetry install --with dev
poetry run pytest uniko-agent/tests pandas-analyst/tests/test_analysis_memory.py -q
poetry run pytest showcase/tests/test_uniko_research_guild.py -q
tox -e format,lint
NO_MKDOCS_2_WARNING=1 poetry run mkdocs build --strict
tox -e test
```

Full CI requires the configured Redis/NATS services and installed Playwright browser. Use dedicated test services and the repository's declared environment flags. Record model/hardware requirements and run real-model gates explicitly when standard CI skips expensive or credential-dependent work. Build affected packages and verify portable dependency metadata when public contracts or runtime distributions change.

## Implementation sequence and release checklist

1. Fix P0 contract defects and add native regressions. Settle record identity/provenance and null-scope semantics before expanding ingestion.
2. Unify configuration and effective capability reporting. Update examples with only supported fields.
3. Complete core source ingestion, bounded retrieval, answers and lifecycle; run G1 sequential Guild/restart tests.
4. Add structured experience and source navigation; verify G2.
5. Validate BGE-M3 on a fresh store and intended hardware; verify G3 independently of upstream resource optimization.
6. Select native or external OCR/media profiles, preserve original sources, and verify G4/G5.
7. Measure operational scale and adopt upstream improvements as their releases become available; verify G6.

- [ ] Every advertised capability maps to a verified gate or an explicit unavailable/deferred state.
- [ ] Each task has an assignee and linked implementation/test evidence.
- [ ] Request models, exports, schemas, examples and routes agree.
- [ ] Unsupported settings fail clearly instead of being silently ignored.
- [ ] Ingest/recall/answer failures and fallbacks have explicit observable outcomes.
- [ ] Persistence, deletion, isolation and shutdown tests pass with native dependencies.
- [ ] Relevant skips/xfails/xpasses are reviewed; no feature is declared complete from unrelated CI totals.
- [ ] Selected CPU/GPU/OCR/media profiles have installation and execution evidence.
- [ ] Upstream issue states and required versions are refreshed.
- [ ] Package build, lint/types, strict docs and appropriate full regression CI pass.

## Decisions to close during implementation

| Decision | Proposed direction | Gate |
| --- | --- | --- |
| One config authority | Engine settings in native resolver config; supported per-query overrides in typed requests | G1 |
| Provenance migration | Native category/source/revision first; explicitly support existing stored Rustic record identities | G1 |
| Answer policy | Generate from the exact authorized bounded context; use Rustic LLM dependencies when native answer cannot enforce it | G1 |
| Media extraction location | Narrow extraction dependencies with original bytes in filesystem storage and explicit derivation identity | G4/G5 |
| OCR runtime | Verified upstream wheel/build or external extractor; do not infer support from accepted config | G4 |
| Scale target | Set concurrency/memory/latency budgets from the intended deployment and measured profiles | G6 |
| Extended reasoning surface | Expose only selected authorized operations with use cases and tests | G2 |

## Source map and maintenance

- [Resolver baseline](https://github.com/milliondreams/rustic-ai/blob/7bc3cf0/uniko-agent/src/rustic_ai/uniko_agent/resolver.py)
- [MemoryAgent baseline](https://github.com/milliondreams/rustic-ai/blob/7bc3cf0/uniko-agent/src/rustic_ai/uniko_agent/agent.py)
- [Public requests and responses](https://github.com/milliondreams/rustic-ai/blob/7bc3cf0/uniko-agent/src/rustic_ai/uniko_agent/models.py)
- [LLM memory wrapper](https://github.com/milliondreams/rustic-ai/blob/7bc3cf0/uniko-agent/src/rustic_ai/uniko_agent/memories.py)
- [Uniko Blackbook](https://github.com/rustic-ai/uniko/blob/28f8a1ae3e343f62392800b7d693c0bac45c7c80/docs/BLACKBOOK.md)
- [uni-xervo runtime](https://github.com/rustic-ai/uni-xervo/blob/fd312158599cb3fe429e93c56f07f7124d216642/crates/uni-xervo/src/runtime.rs)

Update this plan in the same PR as a task's implementation. Change its state, link acceptance evidence and refresh affected feature claims. Preserve the evidence baseline when adding a newer run; do not replace an unverified capability with a broad statement that all CI is green.


## G2 implementation and acceptance evidence

G2 uses Uniko 0.5.1 native APIs for tool calls, actions, episodes, explicit
observations/facts, deterministic consolidation, atomic multi-turn units,
procedure matching/feedback and bounded rule/experience reads. Reporting actor
identity is the authenticated message sender. Goal/task creation assigns stable
external IDs before writing; native transitions retain their actual boolean,
status, phase and timestamps. Native `done` status is not relabelled.
Unsupported goal metadata, pause/resume, multiple task dependencies and task
outcome controls are rejected. Goal context exposes recent message text and
native sessions/facts/entities; episode context remains explicitly unavailable.

The private runtime owns a SQLite operation journal beside persistent graph
storage. In-memory storage uses an in-memory journal. It claims commands before
native dispatch, saves compact results before publishing replies, rejects
changed payloads and unmanaged existing native IDs, and replays completed
commands without repeating effects. Goal/task creation replay returns current
native state. Interrupted or ambiguous effects remain `operation_outcome_unknown`
after restart; no automatic retry is attempted. Journal and native graph commits
cannot be atomic, so an unknown outcome requires native inspection. Preserve
both in backups. Receipt retention follows private-store retention.

Units prepare all sources before dispatch and enforce 128 turns, 32 aggregate
attachments and a configurable default 32 MiB prepared budget. Streamed batches
retain per-item terminal outcomes; embedded-tool items use separate atomic units
and receipts. An in-flight uncertain item retains its operation identity and
uses `stored: null`; unstarted cancelled items use `stored: false`. Summaries
report `uncertain_count` separately from known stored `submitted_count`.
Store-wide consolidation, invalidation and procedure feedback
require `control_producers`. Explicit owner selection requires `scope_producers`.
Scoped/visible evidence is validated before dereferencing; unsupported native
scope dimensions fail closed rather than broaden access. [U67](https://github.com/rustic-ai/uniko/issues/67)
tracks dedicated registration; the interim path uses the resolver's actual
organization, creates no synthetic messages/actions, and reports unknown native
participant kind honestly. U63's optional LLM consolidation remains deferred.

Evidence is committed in
[test_g2_structured.py](https://github.com/milliondreams/rustic-ai/blob/main/uniko-agent/tests/test_g2_structured.py)
and [test_g2_routed.py](https://github.com/milliondreams/rustic-ai/blob/main/uniko-agent/tests/test_g2_routed.py).
Native tests cover fresh-store registration, ownership rejection, real IDs,
causal and fact-support edges, learned procedures, feedback replay, actual
store/journal restart, changed-payload conflicts, unknown effects, cancellation,
prewrite attachment/budget rejection and bounded reads. The real Guild bus test
routes typed commands/replies between a reporting agent and MemoryAgent with
production sender filtering, one terminal reply per command, replay, lifecycle
updates, serialized native task priority and partial batch outcomes. Goal listings
exclude records with conflicting native owners before reading their views.
Fault-injection regressions preserve unknown outcomes after native commits and
original cancellation when both journal completion and uncertainty updates fail;
the durable pending claim prevents duplicate dispatch. Existing research/analyst tool producers are
not automatically instrumented; they can adopt these typed contracts separately.


Uniko 0.5.1 attributes embedded tool calls to their turn sender. Until
[U68](https://github.com/rustic-ai/uniko/issues/68) adds an independent performer
override, turns containing tools must use the authenticated reporting agent as
`sender_id`. A unit can include a separate user turn and a reporting-agent turn
whose tool call references that user's message with `triggered_by`. Standalone
`RecordToolCallRequest` can also reference a user's previously stored message.
Mismatched embedded-tool senders are rejected before any native write; user
message attribution is never rewritten to satisfy tool ownership.


Final local acceptance on 2026-11-17 (macOS ARM64, Python 3.13.12):
`tox -e test -- --workers 4` passed with **2,020 passed, 88 skipped,
3 xfailed and 2 xpassed** using Redis and NATS/JetStream. The existing expensive,
credential-dependent and incomplete tests retain their configured exclusions.
`tox -e format,lint` passed (701 files checked by mypy), strict MkDocs passed,
and the final source distribution/wheel built with all five matching schemas.
All 25 lockfiles remained fresh. Eighteen G2 regressions passed, including eight
cases added for the selected review findings. The expanded actual-store restart
test separately verified tool IDs, episode causal links,
facts, goals and receipt replay after close/reopen. These checks do not certify
G3–G6 or untested platform/provider combinations.
