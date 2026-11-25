# Uniko Research Guild message flow

The current user guide is [Uniko MemoryAgent](../../docs/agents/uniko/index.md), with a [protocol reference](../../docs/agents/uniko/protocol.md) and [resolver guide](../../docs/dependencies/uniko/index.md). This page describes the checked-in [blueprint](../apps/uniko_research_guild.json) and [UnikoResearchCoordinator](../src/rustic_ai/showcase/uniko_research.py).

## Ownership

MemoryAgent owns typed cognitive-memory execution. Uniko owns native extraction, provenance, consolidation, and recall. The coordinator owns each request's original question, authenticated User Proxy identity, request session, ingestion barrier, research decisions, and terminal response. Provider agents own search/scrape/synthesis execution.

Incoming `ChatCompletionRequest` first passes through `MemoryRequestInitializerAgent`, which preserves the exact transport request ID as a decimal string and derives an `analysis-…` session from guild, User Proxy sender, and request identity. Routing expressions must preserve this initialized context rather than rebuilding it from numeric IDs.

## Sequence

1. The coordinator records the user input and recalls bounded evidence using the original question and request session.
2. If the current recall is sufficient, it supplies the original question and exact bounded context to the synthesis LLM. The existing heuristic is a score above 0.05; it is not a correctness guarantee.
3. Otherwise, it dispatches research requests and tracks their expected search/scrape outputs. Successful file enumeration creates ingestion items; failed enumeration remains an explicit outcome.
4. Each usable source becomes a bounded `IngestDocumentRequest`. `IngestOutcome` or `MemoryAgentError` resolves that item's barrier state. `stored` and `searchable` remain distinct.
5. Only after the expected enumeration and ingestion outcomes settle does the coordinator recall again and synthesize from the original question and returned evidence.
6. It records the final visible response, finalizes the request session, and emits the terminal user presentation through guild routes. Duplicate and late outcomes cannot restart a completed workflow.

Requests and observations carry the coordinator's request/session/stage/item context. The memory agent returns typed facts and outcomes; it does not decide that the user's research task is complete.

## Memory and source scope

The memory store is private to its agent. Shared scrape files are read through the guild filesystem; native storage uses the separate agent filesystem. Record kinds distinguish user assertions, external evidence, model interpretations, deterministic observations, executed results, and assistant responses. Scope selection and producer permissions are configured by the guild.

Remote URLs are fetched by research capabilities before ingestion. A retained empty document is not usable evidence. Recall returns bounded source attribution and explicit compatibility limits; no stage invents missing source metadata.

## Deployment and validation

Configure research and synthesis providers separately from memory's local models. Streaming is disabled in the blueprint; direct observation/ingestion does not need a streaming flush. Native model startup is best effort, and accepted configuration does not certify OCR, hybrid retrieval, GPU execution, or multimodal extraction.

Behavioral coverage is in [test_uniko_research_guild.py](../tests/test_uniko_research_guild.py). The broader native and typed contract evidence is recorded in the [implementation/completion plan](../../docs/design/uniko-agent-completion.md). Strict blueprint parsing is a structural check; complete research requires configured providers and executable success/failure paths.
