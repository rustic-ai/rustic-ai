# Examples and Usage

## Phase 2 Implementation Complete

Phase 2 of the Uniko Memory Agent is now complete with **12 processors** and **30 payload models**. The implementation includes:

- ✅ Observation & Recall (Phase 1)
- ✅ Document ingestion (Phase 2)
- ✅ Goal management (Phase 2)
- ✅ Task management (Phase 2)
- ✅ Batch submission (Phase 2)

## Testing the Implementation

**The best way to see Phase 2 in action is through the comprehensive test suite.**

All Phase 2 features are fully functional and tested:

```bash
cd /home/nihal/Projects/ai-platform/rustic-ai/uniko-agent

# Run all tests
poetry run pytest tests/ -v

# Run specific test suites
poetry run pytest tests/test_memory_agent.py -v      # Phase 1 unit tests
poetry run pytest tests/test_integration.py -v       # Phase 2 integration tests
```

**Note:** The `examples/` directory contains example code, but due to the complexity of the guild messaging infrastructure, the integration tests in `tests/test_integration.py` provide the most complete and working demonstrations of all features.

## Integration Tests

The integration tests in `tests/test_integration.py` demonstrate:

### 1. Complete Research Workflow
```python
test_complete_research_workflow()
```
- Creates research goal with metrics
- Creates tasks with priorities
- Observes research findings
- Recalls knowledge
- Completes tasks with outcomes

### 2. Document Ingestion
```python
test_ingest_document_from_path()
test_batch_submit_turns()
```
- Ingests markdown/PDF documents
- Batch submission of multiple turns
- Efficient bulk observation

### 3. Goal & Task Management
```python
test_create_nested_goals()
test_goal_lifecycle()
test_get_goals_by_phase()
test_task_dependencies()
```
- Parent/child goal relationships
- Complete lifecycle: create → start → complete
- Filtering by phase (active, completed)
- Task dependencies

## Usage in Production

For production use with actual guilds, the pattern is:

```python
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.guild.dsl import DependencySpec
from rustic_ai.uniko_agent import (
    MemoryAgent,
    MemoryAgentConfig,
    ObserveTurnRequest,
    RecallRequest,
    CreateGoalRequest,
)

# 1. Configure uniko dependency (guild-scoped)
uniko_dep = DependencySpec(
    class_name="rustic_ai.uniko_agent.UnikoResolver",
    properties={
        "storage_path": "./data/memory/{org_id}/{guild_id}",  # Persistent
        "llm_spec": {
            "alias": "openai",
            "model_id": "gpt-4o-mini",
            "key_env": "OPENAI_API_KEY"
        },
        "streaming": False,
    }
)

# 2. Build memory agent spec
memory_agent_spec = (
    AgentBuilder(MemoryAgent)
    .set_id("memory_agent")
    .set_name("Memory Agent")
    .set_description("Cognitive memory with goals and tasks")
    .set_properties(MemoryAgentConfig(auto_flush=True))
    .set_dependency_map({"uniko": uniko_dep})
    .build_spec()
)

# 3. Build and launch guild
guild = (
    GuildBuilder("research-guild", "Research Guild", "Research with memory")
    .set_execution_engine("rustic_ai.core.guild.execution.sync.sync_exec_engine.SyncExecutionEngine")
    .add_agent_spec(memory_agent_spec)
    .add_agent_spec(serp_agent_spec)  # Other agents
    .add_agent_spec(llm_agent_spec)
    .launch(organization_id="your-org-id")
)

# 4. Use with guild messaging system
# Messages are routed through the guild's messaging infrastructure
# See research guild blueprint for routing patterns
```

## Key Features

### Guild-Scoped Memory
All agents in a guild share the same memory graph:
- `LLMAgent` can recall context
- `SERPAgent` results are observed
- `MemoryAgent` manages goals/tasks
- All access the same knowledge base

### Persistent Storage
Configure `storage_path` in `UnikoResolver` for persistent memory:
```python
"storage_path": "./data/memory/{org_id}/{guild_id}"
```

Placeholders:
- `{org_id}` - Organization ID
- `{guild_id}` - Guild ID

### LLM Integration
Configure `llm_spec` for answer generation:
```python
"llm_spec": {
    "alias": "openai",  # or "mistral"
    "model_id": "gpt-4o-mini",
    "key_env": "OPENAI_API_KEY"
}
```

## API Reference

See [README.md](README.md) for complete API documentation of all 12 processors and 30 payload models.

## Next Steps

- **Run tests**: `poetry run pytest tests/ -v`
- **Review integration tests**: See `tests/test_integration.py` for complete examples
- **Integrate with research guild**: Route SERP/Playwright results to memory
- **Add Phase 3 features**: Advanced queries, data access, logic rules

## Support

For issues or questions:
- Check test files for usage examples
- See README.md for API documentation
- Review integration tests for workflow patterns
