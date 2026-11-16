# Uniko Memory Agent

Comprehensive memory agent for Rustic AI that integrates [uniko](https://github.com/uniko-ai/uniko)'s cognitive memory system.

## Overview

The Uniko Memory Agent integrates uniko's memory system into the Rustic AI guild framework. Current coverage, known gaps and acceptance gates are tracked in the [implementation and completion plan](../docs/design/uniko-agent-completion.md). It enables:

- **Zero-cost knowledge ingestion** (local ONNX embeddings, no LLM API calls)
- **Multi-phase recall** (3-phase cascade: Facts/Procedures → Episodes/Observations → Chunks)
- **Full provenance tracking** (every fact traces back to source messages)
- **Goal and task management** (research workflows with working memory)
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

This integration supports Uniko 0.5.1 through the 0.5 release series.
The embedded `mistralrs` runtime is no longer supported. Old `alias: mistral`
configurations are rejected; they are not migrated to the hosted Mistral API.
The base `uniko` wheel runs local ONNX memory models on CPU. Uniko also
publishes mutually exclusive `uniko-metal` (macOS ARM64) and `uniko-cuda`
(Linux x86-64) distributions; install one runtime distribution per environment.

```bash
cd rustic-ai/uniko-agent
poetry install --with dev
```

## Quick Start

### 1. Basic Usage with In-Memory Storage

```python
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.guild.dsl import DependencySpec
from rustic_ai.uniko_agent import MemoryAgent, MemoryAgentConfig, ObserveTurnRequest, RecallRequest

# Configure uniko dependency (agent-scoped, in-memory)
uniko_dep = DependencySpec(
    class_name="rustic_ai.uniko_agent.UnikoResolver",
    properties={
        "storage_path": None,  # In-memory
        "llm_spec": None,  # Optional LLM for Q&A
        "streaming": False,
    }
)

# Build guild with memory agent
guild = (
    GuildBuilder(guild_id="research-guild", guild_name="Research Guild", guild_description="...")
    .set_dependency_map({"uniko": uniko_dep})
    .add_agent(
        AgentBuilder(MemoryAgent)
        .set_id("memory_agent")
        .set_config(MemoryAgentConfig(auto_flush=True))
        .build_spec()
    )
    .build_guild(organization_id="org123")
)

# Observe conversation turns
guild.send_message(
    ObserveTurnRequest(
        sender_id="user",
        content="I prefer working in Python over JavaScript",
        metadata={"topic": "programming"}
    ),
    agent_id="memory_agent"
)

# Recall knowledge
guild.send_message(
    RecallRequest(query="user programming preferences"),
    agent_id="memory_agent"
)
```

### 2. Persistent Storage

```python
uniko_dep = DependencySpec(
    class_name="rustic_ai.uniko_agent.UnikoResolver",
    properties={
        "storage_path": "memory",  # Within the injected agent filesystem
        "llm_spec": {
            "provider": "openai_with_key_env",
            "alias": "answer/default",
            "model_id": "gpt-4o-mini",
            "key_env": "OPENAI_API_KEY"
        },
        "streaming": False,
    }
)
```

### 3. Answer Questions with LLM

```python
from rustic_ai.uniko_agent import AnswerRequest

# Requires LLM configured in UnikoResolver
guild.send_message(
    AnswerRequest(question="What programming language does the user prefer?"),
    agent_id="memory_agent"
)

# Response includes:
# - Generated answer text
# - Recalled context (RecallResponse)
# - Citations with provenance chain
```

## Processor API

The MemoryAgent exposes 12 processors across Phase 1 and Phase 2:

### Observation

- **`observe_turn`** (`ObserveTurnRequest` → `ObserveResult`)
  - Ingest conversation turns with NLP extraction (entities, observations)
  - Supports attachments (PDFs, documents)
  - Auto-flushes by default

### Recall

- **`recall_knowledge`** (`RecallRequest` → `RecallResponse`)
  - 3-phase cascade recall (facts → episodes → chunks)
  - Configurable max tokens, phase restrictions
  - Optional scope filtering (sessions, participants, time range)

### Answer

- **`answer_question`** (`AnswerRequest` → `AnswerResponse`)
  - Generate LLM answers using recalled context
  - Requires LLM configured in resolver
  - Returns answer + context + citations

### Document Ingestion (Phase 2)

- **`ingest_document`** (`IngestDocumentRequest` → `IngestOutcome`)
  - Ingest PDFs, markdown, HTML documents
  - Automatic chunking and entity extraction
  - Supports local paths, URLs, and byte content

- **`batch_submit`** (`BatchSubmitRequest` → `BatchSubmitResponse`)
  - Submit multiple turns in batch (streaming mode)
  - More efficient than individual observations
  - Optional flush after submission

### Goal Management (Phase 2)

- **`create_goal`** (`CreateGoalRequest` → `GoalView`)
  - Create research goals with metrics and guardrails
  - Supports nested goals (parent/child relationships)
  - Optional deadlines and success criteria

- **`update_goal`** (`UpdateGoalRequest` → `GoalStatusResponse`)
  - Update goal status: start, complete, abandon, pause, resume
  - Track outcomes and metadata
  - Full lifecycle management

- **`get_goals`** (`GetGoalsRequest` → `GoalsListResponse`)
  - List goals by phase (all, active, completed, abandoned)
  - Filter by parent goal
  - Limit results

### Task Management (Phase 2)

- **`create_task`** (`CreateTaskRequest` → `TaskView`)
  - Create tasks for goals
  - Set priority (1-5) and dependencies
  - Track task hierarchy

- **`update_task`** (`UpdateTaskRequest` → `TaskStatusResponse`)
  - Update task status: start, complete, abandon, block, unblock
  - Record outcomes
  - Manage task lifecycle

- **`get_goal_context`** (`GoalContextRequest` → `GoalContext`)
  - Get goal working memory
  - Includes tasks, episodes, and progress metrics
  - Full context for research workflows

## Configuration

### MemoryAgentConfig

```python
from rustic_ai.uniko_agent import MemoryAgentConfig

config = MemoryAgentConfig(
    default_session_id=None,        # Defaults to guild_id
    recall_max_tokens=2000,          # Max tokens in recall bundle
    recall_phase1_only=False,        # Restrict to facts/procedures
    answer_max_tokens=500,           # Max tokens for answers
    auto_flush=True,                 # Auto-flush observations
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

Generation supports the Python SDK's three modes: `openai` (default key env),
`openai_with_key_env`, and `llamacpp`. `alias` is a runtime model name, separate
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
when compiled into the runtime. Uniko 0.5.1's Python `LlmSpec` constructors
expose only OpenAI-compatible and llama.cpp generation, so the resolver does
not advertise the other providers as direct `llm_spec` modes. Merely adding a
generation entry to a catalog does not select it for `Agent.answer`.

## Integration with Research Guild

Memory agent is designed for research workflows:

```python
from rustic_ai.core.guild.dsl import RoutingSlip, RouteBuilder

# Route search results to memory
guild_builder.add_routing_rule(
    RouteBuilder(AgentTag(id="serp_agent"))
    .on_message_format(SERPResults)
    .set_payload_transformer(
        output_type=ObserveTurnRequest,
        payload_xform=JxScript({
            "sender_id": "serp_agent",
            "content": JExpr("$.results | [*].snippet | join('\n')")
        })
    )
    .set_destination(agent_id="memory_agent")
    .build()
)
```

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
- `max_tokens`: Optional token limit
- `phase1_only`: Restrict to facts/procedures
- `scope`: Optional filters (sessions, participants, time)

### AnswerRequest
- `question`: Question to answer
- `max_tokens`: Optional answer length
- `scope`: Optional recall scope

### Error Handling

Errors return `MemoryAgentError`:
```python
{
    "error": "llm_not_configured",
    "message": "LLM not configured...",
    "details": {"question": "..."}
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

### Guild-Scoped Memory

- One private `uniko.Uniko` store per organization, guild, and agent
- Persistent storage is resolved from the injected agent filesystem, never cwd
- Other agents share memory through typed requests to MemoryAgent
- Incoming documents are read from the separate guild-scoped filesystem

### Dependency Injection

```
GuildSpec
  └─ dependency_map["uniko"] = UnikoResolver  (agent-scoped)
       └─ resolve(org_id, guild_id, agent_id) → uniko.Agent
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
       └─ uniko_agent.recall(query, config)
       └─ RecallResponse (ranked items with provenance)
```

## Phase 2 Example

See `examples/research_workflow_example.py` for a complete demonstration of:
- Creating goals with metrics and guardrails
- Managing tasks with priorities
- Batch submission of findings
- Document ingestion
- Goal context retrieval

```bash
cd examples
python research_workflow_example.py
```

## Future Enhancements (Phase 3+)

Planned features:

- **Advanced queries** (`query_graph` for Cypher queries)
- **Data access** (`get_message`, `get_artifact`)
- **Deletion** (`delete_session`, `forget_participant`)
- **Logic rules** (Locy rule definition and execution)
- **Procedure learning** (auto-promote successful patterns)

## References

- [Uniko Documentation](https://uniko.ai/docs)
- [Rustic AI Core](https://github.com/dragonscale-ai/rustic-ai)
- [Uniko GitHub](https://github.com/uniko-ai/uniko)

## License

Apache 2.0 - see LICENSE file
