# Uniko Memory Agent

Comprehensive memory agent for Rustic AI that leverages [uniko](https://github.com/uniko-ai/uniko)'s cognitive memory system.

## Overview

The Uniko Memory Agent provides a complete integration of uniko's 5-tier memory system (Episodic, Semantic, Procedural, Provenance, Meta-Memory) into the Rustic AI guild framework. It enables:

- **Zero-cost knowledge ingestion** (local ONNX embeddings, no LLM API calls)
- **Multi-phase recall** (3-phase cascade: Facts/Procedures → Episodes/Observations → Chunks)
- **Full provenance tracking** (every fact traces back to source messages)
- **Goal and task management** (research workflows with working memory)
- **Guild-scoped memory sharing** (all agents in a guild access shared knowledge)

## Installation

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

# Configure uniko dependency (guild-scoped, in-memory)
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
        "storage_path": "./data/memory",  # Persistent
        "org_level": True,   # Append org_id to storage_path
        "guild_level": True, # Append guild_id to storage_path
        "llm_spec": {
            "alias": "openai",
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
    "storage_path": str | None,      # None = in-memory, str = base path
    "org_level": bool,               # Append org_id to storage_path
    "guild_level": bool,             # Append guild_id to storage_path
    "llm_spec": dict | None,         # LLM config for answer generation
    "streaming": bool,               # Enable streaming mode
    "scope_to_agent": bool,          # Scope memory to individual agents (not recommended)
}
```

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

- One `uniko.Uniko` instance per guild
- All agents in guild share memory graph
- Guild ID maps to uniko agent ID
- Enables collaborative memory across LLMAgent, KnowledgeAgent, etc.

### Dependency Injection

```
GuildSpec
  └─ dependency_map["uniko"] = UnikoResolver  (guild-scoped)
       └─ resolve(org_id, guild_id, agent_id) → uniko.Agent
            └─ Returns guild-scoped agent handle
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
