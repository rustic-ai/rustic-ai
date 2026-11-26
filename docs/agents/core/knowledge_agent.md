# KnowledgeAgent retirement and migration

KnowledgeAgent, the core knowledge-base implementation and `rusticai-lancedb`
are retired from the source tree. Use [Uniko MemoryAgent](../uniko/index.md) for
native document ingestion, attributed recall and memory lifecycle, and the
[document coordinator](../uniko/documents.md) for correlated multi-source workflows.

Both [PaperBanana v2](../../showcase/paper_banana.md) and
[Semantic Memory Assistant v2](../../showcase/semantic_memory_assistant.md) use
these capabilities. This page retains the previous documentation URL to help
users migrate saved specifications.

## Removed public contracts

| Retired surface | Replacement or migration disposition |
| --- | --- |
| KnowledgeAgent; `CatalogMediaLinks`, `CatalogMediaResults`, `IndexMediaLinks`, `IndexMediaResult`, `IndexMediaResults`, `KBTarget`, `KBSearchRequest`, `KBSearchResults` | `DocumentWorkflowRequest` for coordinated ingestion/recall; direct `IngestDocumentRequest` and `RecallRequest` for individual operations |
| KnowledgeBase, Knol, catalog managers and the core knowledge-base configuration, pipeline and query types | Ordinary source files plus Uniko source, revision and record identities |
| In-memory KB backend and the knowledge-base resolver namespace | `UnikoResolver` with explicit agent ownership and persistent local storage |
| LanceDB package and backend/resolver | Native Uniko ingestion and recall |
| KnowledgeBasedMemoriesStore and `kb_backend` | `UnikoMemoriesStore`; conversational storage remains owned by the LLM agent |
| Arbitrary table targets, custom chunk/embedding pipelines, weighted targets, backend filters and hybrid/reranking controls | Retired; use supported Uniko scopes, record kinds and recall bounds |

Removed contracts have no compatibility aliases or legacy protocol adapter.
Independent VectorAgent, Chroma, generic VectorStore/Embeddings, media and
filesystem capabilities remain available. Uniko does not automatically import
old LanceDB or Knol stores or translate old filters and schema definitions.

## Typed replacement examples

Configure a DocumentCoordinator with a stable corpus session and an explicit
MemoryAgent ID. Configure the MemoryAgent's Uniko dependency separately; see the
[executable document guild](https://github.com/milliondreams/rustic-ai/blob/main/uniko-agent/examples/document_guild.py).

```python
from rustic_ai.uniko_agent import DocumentWorkflowRequest, MemorySource

request = DocumentWorkflowRequest(
    request_id="harbor-reference-1",
    sources=[MemorySource(
        source_id="harbor-plan",
        path_hint="harbor.md",
        mime_type="text/markdown",
        text="Harbor pilot budget is CAD 42000. Mina Patel coordinates it.",
    )],
    query="What is the Harbor pilot budget and who coordinates it?",
)
```

Publish that request to the coordinator's configured request topic. It returns
`DocumentWorkflowResult` with per-source ingestion outcomes and bounded evidence,
or `DocumentWorkflowError` through `ctx.send_error`. A stored source is not
necessarily searchable. Supply no query for ingestion-only requests; supply no
sources to recall from the configured corpus.

For direct recall through MemoryAgent:

```python
from rustic_ai.uniko_agent import MemoryScope, RecallRequest

request = RecallRequest(
    query="Harbor pilot budget",
    scope=MemoryScope(sessions=["corpus:harbor:references"]),
    allowed_record_kinds=["external_evidence"],
    item_limit=10,
    max_characters=6000,
    token_budget=2000,
)
```

Use `SourceReadRequest` for read, outline or original-content operations with
returned source identities. Use `ForgetMemoryRecordRequest` with
`kind="external_evidence"` for document removal, or `DeleteMemorySessionRequest`
for corpus removal. Deletion is an explicit operation, never a migration side
effect. See the [message protocol](../uniko/protocol.md) for complete I/O schemas.

## Existing deployments and saved guilds

1. Inventory saved GuildSpecs, catalog blueprints, corpus files, Knol manifests,
   LanceDB stores and legacy conversation records before upgrading.
2. Preserve the existing stores and a working old-release export environment.
   The [pre-retirement source snapshot](https://github.com/milliondreams/rustic-ai/tree/918d9d403b2e9f0f08569655af7201271955cfcc)
   remains available. Retain metadata and an export/import journal when required.
3. Reimport the v2 consumer blueprints or rewrite custom agents, resolvers,
   message formats and routes to the typed Uniko contracts. Remove `kb_backend`
   and the retired memory plugin. A class-name substitution alone is insufficient.
4. Stage remote source content into the configured guild filesystem. Configure
   stable organization/guild/agent identities, persistent local native volumes,
   one process owner and backups. Guild/deployment design owns access policy and
   acquisition credentials.
5. Reingest sources under stable source IDs and verify hashes/counts, provenance,
   stored/searchable outcomes, current revisions, source reads and close/reopen.
   Keep old stores for rollback until deployment cutover is verified.
6. Drain active old guilds before installing the declared breaking release. If
   inventory establishes no legacy data or saved specifications, verify a fresh
   deployment instead.

Unfinished application workflows are transient; replacing a blueprint does not
resume an old workflow. The [migration plan](../../design/knowledge-agent-uniko-migration.md)
separates repository retirement, broad acceptance and deployed-data cutover.

## Publication gate

Phase 4 removes source APIs without changing package versions. These builds are
for local verification and must not be published under the existing compatibility
promise. A separate release task must select a coordinated breaking release,
update dependent package versions/constraints and refresh affected locks before
publication. Repository cleanup does not establish deployment readiness and
performs no stored-data deletion.
