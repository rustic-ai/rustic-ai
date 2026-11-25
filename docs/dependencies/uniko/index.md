# UnikoResolver

`rustic_ai.uniko_agent.resolver.UnikoResolver` provides lifecycle-managed native handles for [MemoryAgent](../../agents/uniko/index.md) and `UnikoMemoriesStore`. Resolution caches a separate private Uniko store for each organization/guild/agent identity. Other agents collaborate through messages; dependency declaration at guild level does not create a shared native graph.

## Configuration

| Property | Default | Meaning |
| --- | --- | --- |
| `storage_path` | `None` | Disposable native storage or a location within the injected private agent filesystem |
| `llm_spec` | `None` | Optional SDK-native generation configuration |
| `streaming` | `False` | Enable background streaming operations |
| `scope_to_agent` | `False` | Native agent identity uses guild ID by default, or Rustic agent ID when true; storage stays private in both modes |
| `config` | `None` | Partial native configuration |
| `embedding` | `None` | Native preset/section overriding `config.embedding` |
| `nlp` | `None` | Native preset/section overriding `config.nlp` |
| `reranker` | `None` | Preserve defaults; use a preset/section, or `False` to disable; `True` is rejected |
| `readiness_policy` | `sdk_default` | Best-effort SDK warmup; `require_verified` is unavailable |

## Persistent local storage

Configure these on the memory agent. The `filesystem` key resolves privately at agent scope; document ingestion additionally uses the guild-scoped filesystem for incoming shared files.

```python
from rustic_ai.core.guild.dsl import DependencySpec

memory_dependencies = {
    "filesystem": DependencySpec(
        class_name="rustic_ai.core.guild.agent_ext.depends.filesystem.filesystem.FileSystemResolver",
        properties={"protocol": "file", "path_base": "/tmp/rustic-memory", "storage_options": {}},
    ),
    "uniko": DependencySpec(
        class_name="rustic_ai.uniko_agent.UnikoResolver",
        properties={"storage_path": "memory", "streaming": False, "llm_spec": None},
    ),
}
```

The resolver translates the injected filesystem URI into a native path and rejects non-local backing storage. Keep organization, guild, and agent identities stable across restart. Store-relative `storage_path` is not an arbitrary host path or a way to read shared document files. Native compatibility checks are authoritative; incompatible stores need explicit migration. Back up the `.rustic-operations.sqlite3` journal with the store.

## Models and generation

The CPU wheel supports local embedding/NLP memory pipelines without a generation API. Initial use can load/download model assets; deployment should cache assets and the `cl100k_base` tokenizer when offline use is required. Configuration acceptance is not verified model readiness.

```python
model_properties = {
    "embedding": "bge-small",
    "nlp": "v1",
    "reranker": False,
    "llm_spec": {
        "provider": "openai_with_key_env",
        "alias": "answer/default",
        "model_id": "gpt-4o-mini",
        "key_env": "OPENAI_API_KEY",
    },
}
```

`llm_spec` is optional and needed only for `AnswerRequest` SDK-native generation. The exposed generation modes are `openai`, `openai_with_key_env`, and `llamacpp`. An alias names the runtime model; it is separate from provider and `model_id`. OpenAI-compatible endpoints can supply `base_url`; llama.cpp runs in an external OpenAI-compatible `llama-server`. Old `alias: openai` inputs remain supported. `alias: mistral`/`mistralrs` embedded-runtime inputs are rejected, not migrated to hosted Mistral.

Custom uni-xervo catalogs can select supported native tasks/providers compiled into the runtime. A catalog generation entry alone does not select the model used by `Agent.answer`. The direct Python `llm_spec` modes are narrower than the full native provider catalog.

`catalog_path`, `schema_path`, and `observation_rules_path` in native `config` require readable absolute local files and are validated before persistent store opening. Custom catalogs replace defaults and must include required embedding/NLP/reranker aliases for enabled pipelines. Embedding dimension changes require a fresh store. Metal/CUDA wheels remain outside the validated Rustic dependency profile; BGE-M3 dense/sparse/ColBERT certification is a separate acceptance gate.

## Lifecycle and diagnostics

Handles reserve accepted native operations. `resolver.shutdown()` stops new work, drains accepted work, drops cached handles, and shuts down native instances. Use `await resolver.shutdown_async()` when active work must drain on an event loop. Cleanup is idempotent; failures from externally retained raw native handles remain visible. Explicit lifecycle ownership is preferable to relying on destructor cleanup.

`EffectiveConfigRequest`, `CapabilityRequest`, and `MemoryHealthRequest` return `MemoryDiagnostics`, separating configured settings, observed SDK information, and unknown provider/warmup/adapter availability. Do not infer OCR, multimodal processing, GPU acceleration, or readiness from those configuration fields.

See the [message protocol](../../agents/uniko/protocol.md) for bounds, trust controls, and reconciliation.
