# LLM Agent Memory Stores

Memory stores provide extended memory capabilities for LLM agents, allowing them to recall past conversations, access shared state, or perform semantic search over conversation history.

## Overview

Memory stores are specialized plugins that implement the `MemoriesStore` interface, which extends `LLMCallWrapper`. They operate in the preprocessing phase to inject relevant memories into the LLM context, and in the postprocessing phase to store new messages for future recall.

All memory stores implement two core methods:

- **`remember()`**: Store a message for future retrieval
- **`recall()`**: Retrieve relevant messages based on the current context

## Memory Store Comparison

| Store Type | Persistence | Scope | Best For |
|------------|-------------|-------|----------|
| [QueueBasedMemoriesStore](#queuebasedmemoriesstore) | In-memory only | Agent instance | Simple sliding window memory |
| [HistoryBasedMemoriesStore](#historybasedmemoriesstore) | Via message history | Thread/conversation | Extracting context from message flow |
| [StateBackedMemoriesStore](#statebackedmemoriesstore) | Agent state | Agent | Persistent per-agent memory |
| [GuildStateBackedMemoriesStore](#guildstatebackedmemoriesstore) | Guild state | Guild | Shared memory across agents |
| [KnowledgeBasedMemoriesStore](#knowledgebasedmemoriesstore) | Vector database | Guild | Semantic search over conversations |

## QueueBasedMemoriesStore

The simplest memory store using a fixed-size FIFO queue. Messages are stored in memory and automatically evicted when the queue reaches capacity.

### Configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `memory_size` | `int` | `36` | Maximum number of messages to retain |

### When to Use

- Quick prototyping without persistence requirements
- Short conversations where recent context is sufficient
- Scenarios where memory loss on restart is acceptable

### Python Example

```python
from rustic_ai.llm_agent.memories import QueueBasedMemoriesStore

memory_store = QueueBasedMemoriesStore(memory_size=50)
```

### YAML Configuration

```yaml
llm_request_wrappers:
  - kind: rustic_ai.llm_agent.memories.queue_memories_store.QueueBasedMemoriesStore
    memory_size: 50
```

## HistoryBasedMemoriesStore

Extracts memories from the guild's message history rather than maintaining its own storage. This store reconstructs conversation context from `ChatCompletionRequest` and `ChatCompletionResponse` messages in the enriched history.

### Configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `text_only` | `bool` | `True` | Filter to only include text messages (excludes images, etc.) |

### When to Use

- When you want memories derived from the actual message flow
- Conversations that span multiple agents
- Scenarios where message history is already being tracked

### Python Example

```python
from rustic_ai.llm_agent.memories import HistoryBasedMemoriesStore

memory_store = HistoryBasedMemoriesStore(text_only=True)
```

### YAML Configuration

```yaml
llm_request_wrappers:
  - kind: rustic_ai.llm_agent.memories.history_memories_store.HistoryBasedMemoriesStore
    text_only: true
```

### How It Works

The `remember()` method is a no-op since this store doesn't maintain its own storage. During `recall()`, it:

1. Extracts `enriched_history` from the process context
2. Parses `ChatCompletionRequest` and `ChatCompletionResponse` messages
3. Deduplicates messages by content
4. Optionally filters to text-only content

## StateBackedMemoriesStore

Persists memories to the agent's state store, enabling memory that survives agent restarts. Uses JSON Patch for efficient state updates.

### Configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `memory_size` | `int` | `12` | Maximum number of messages to retain |

### Requirements

The agent must use the `StateRefresherMixin` to enable state persistence.

### When to Use

- Long-running conversations that need persistence
- Agents that may be restarted but need to retain context
- Per-agent memory isolation

### Python Example

```python
from rustic_ai.llm_agent.memories import StateBackedMemoriesStore

memory_store = StateBackedMemoriesStore(memory_size=24)
```

### YAML Configuration

```yaml
llm_request_wrappers:
  - kind: rustic_ai.llm_agent.memories.state_memories_store.StateBackedMemoriesStore
    memory_size: 24
```

### State Structure

Memories are stored under the `memories` key in agent state:

```json
{
  "memories": [
    {"role": "user", "content": "Hello"},
    {"role": "assistant", "content": "Hi there!"}
  ]
}
```

## GuildStateBackedMemoriesStore

Retrieves memories from the guild-level state, enabling shared memory across multiple agents within the same guild.

### Configuration

This store has no additional configuration parameters.

### Requirements

- The agent must use the `StateRefresherMixin`
- Guild state must be configured with a `memories` key

### When to Use

- Shared context across multiple agents in a guild
- Collaborative multi-agent scenarios
- When agents need access to a common conversation history

### Python Example

```python
from rustic_ai.llm_agent.memories import GuildStateBackedMemoriesStore

memory_store = GuildStateBackedMemoriesStore()
```

### YAML Configuration

```yaml
llm_request_wrappers:
  - kind: rustic_ai.llm_agent.memories.guild_state_memories_store.GuildStateBackedMemoriesStore
```

### How It Works

The `remember()` method is a no-op—guild state should be updated through other mechanisms (e.g., a dedicated state management agent). During `recall()`, it reads from `agent.get_guild_state()["memories"]`.

## KnowledgeBasedMemoriesStore

The most sophisticated memory store, using a vector database for semantic search over conversation history. This enables retrieval of contextually relevant memories rather than just recent ones.

### Configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `context_window_size` | `int` | `5` | Number of recent messages to use for building search queries |
| `recall_limit` | `int` | `10` | Maximum number of memories to retrieve |

### Dependencies

This store requires guild-level dependencies that must be configured:

| Dependency | Type | Description |
|------------|------|-------------|
| `filesystem:guild` | `FileSystem` | Filesystem for storing knowledge base data |
| `kb_backend:guild` | `KBIndexBackend` | Vector database backend for semantic search |

### When to Use

- Long conversations where recency isn't the best relevance signal
- Agents that need to recall specific topics from past conversations
- Scenarios requiring semantic similarity matching

### Python Example

```python
from rustic_ai.llm_agent.memories import KnowledgeBasedMemoriesStore

memory_store = KnowledgeBasedMemoriesStore(
    context_window_size=5,
    recall_limit=10,
    depends_on=["filesystem:guild", "kb_backend:guild"]
)
```

### YAML Configuration

```yaml
llm_request_wrappers:
  - kind: rustic_ai.llm_agent.memories.knowledge_memories_store.KnowledgeBasedMemoriesStore
    context_window_size: 5
    recall_limit: 10
    depends_on:
      - filesystem:guild
      - kb_backend:guild
```

### Guild Dependency Configuration

```yaml
dependency_map:
  filesystem:
    class_name: rustic_ai.core.guild.agent_ext.depends.filesystem.FileSystemResolver
    properties:
      base_path: /path/to/guild/storage
    scope: guild
  kb_backend:
    class_name: rustic_ai.chroma.ChromaKBIndexResolver
    properties:
      collection_name: memories
    scope: guild
```

### How It Works

1. **Remember Phase**: Messages are indexed into the knowledge base with metadata (role, timestamp, tool calls, etc.)
2. **Recall Phase**: Recent messages are used to build a semantic search query, and the most relevant past memories are retrieved

## Combining Multiple Memory Stores

You can use multiple memory stores together by adding them to the `llm_request_wrappers` list. They execute in order, with each store's recalled memories being added to the context.

```yaml
llm_request_wrappers:
  # First, add recent queue-based memories
  - kind: rustic_ai.llm_agent.memories.queue_memories_store.QueueBasedMemoriesStore
    memory_size: 10
  # Then, add semantically relevant memories from knowledge base
  - kind: rustic_ai.llm_agent.memories.knowledge_memories_store.KnowledgeBasedMemoriesStore
    context_window_size: 3
    recall_limit: 5
    depends_on:
      - filesystem:guild
      - kb_backend:guild
```

## Creating Custom Memory Stores

To create a custom memory store, extend the `MemoriesStore` base class:

```python
from typing import List, Literal
from rustic_ai.core.guild.agent import Agent, ProcessContext
from rustic_ai.core.guild.agent_ext.depends.llm.models import LLMMessage
from rustic_ai.llm_agent.memories.memories_store import MemoriesStore


class CustomMemoriesStore(MemoriesStore):
    memory_type: Literal["custom"] = "custom"

    # Add custom configuration fields
    custom_param: str = "default_value"

    def remember(self, agent: Agent, ctx: ProcessContext, message: LLMMessage) -> None:
        """Store a message for future retrieval."""
        # Implement storage logic
        pass

    def recall(self, agent: Agent, ctx: ProcessContext, context: List[LLMMessage]) -> List[LLMMessage]:
        """Retrieve relevant messages based on context."""
        # Implement retrieval logic
        return []
```

The base `MemoriesStore` class automatically handles:

- Preprocessing: Calls `recall()` and prepends memories to the request messages
- Postprocessing: Calls `remember()` with the assistant's response

## Related Documentation

- [LLM Agent & Plugins](llm_agent.md) - Overview of the LLM Agent
- [LLM Agent Plugins](llm_agent_plugins.md) - Plugin system architecture
- [Dependency Injection](../howto/dependency_injection.md) - Configuring dependencies
