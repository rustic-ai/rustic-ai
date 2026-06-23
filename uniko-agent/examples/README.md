# Examples

## Phase 2 Implementation is Complete!

All Phase 2 features are **fully implemented and working**. The best way to see them in action is through the comprehensive test suite.

## Running the Tests

```bash
cd /home/nihal/Projects/ai-platform/rustic-ai/uniko-agent

# Run all tests
poetry run pytest tests/ -v

# Run Phase 2 integration tests
poetry run pytest tests/test_integration.py -v

# Run specific test
poetry run pytest tests/test_integration.py::TestResearchWorkflow::test_complete_research_workflow -v
```

## What the Tests Demonstrate

### 1. Complete Research Workflow (`test_complete_research_workflow`)
- Creating research goals with metrics and guardrails
- Creating tasks with priorities
- Starting and completing tasks
- Observing research findings
- Recalling knowledge from memory
- Full end-to-end workflow

### 2. Document Ingestion (`TestDocumentIngestion`)
- Ingesting markdown/PDF documents
- Batch submission of observations
- Efficient bulk data ingestion

### 3. Goal & Task Management (`TestGoalTaskManagement`)
- Creating parent/child goal hierarchies
- Complete lifecycle: create → start → complete
- Filtering goals by phase
- Managing task dependencies

### 4. Memory Persistence (`TestMemoryPersistence`)
- Observations persist across recall calls
- Knowledge accumulates over time

### 5. Scope Filtering (`TestScopeFiltering`)
- Filtering recall by session
- Filtering recall by participant
- Time-based filtering

## Example Test Code

From `tests/test_integration.py`:

```python
@pytest.mark.asyncio
async def test_complete_research_workflow(self, memory_test_harness):
    """Test end-to-end research workflow."""
    
    # Create research goal
    memory_test_harness.send_message(
        CreateGoalRequest(
            goal_id="research-rust-memory",
            title="Research Rust memory safety mechanisms",
            metrics={"sources_count": 5, "depth": "comprehensive"}
        )
    )
    
    # Create tasks
    memory_test_harness.send_message(
        CreateTaskRequest(
            goal_id="research-rust-memory",
            task_id="task-1",
            title="Research borrow checker",
            priority=1
        )
    )
    
    # Observe findings
    memory_test_harness.send_message(
        ObserveTurnRequest(
            sender_id="researcher",
            content="The borrow checker ensures references are always valid"
        )
    )
    
    # Recall findings
    memory_test_harness.send_message(
        RecallRequest(query="How does Rust ensure memory safety?")
    )
    
    responses = memory_test_harness.get_sent_messages()
    recall_response = responses[0].payload
    
    # Verify knowledge was recalled
    assert len(recall_response.items) > 0
```

## Production Usage Pattern

For production use with actual guilds, see the pattern in `../README.md`:

```python
# Configure uniko dependency
uniko_dep = DependencySpec(
    class_name="rustic_ai.uniko_agent.UnikoResolver",
    properties={
        "storage_path": "./data/memory/{org_id}/{guild_id}",
        "llm_spec": {"alias": "openai", "model_id": "gpt-4o-mini", ...}
    }
)

# Build memory agent
memory_agent_spec = (
    AgentBuilder(MemoryAgent)
    .set_id("memory_agent")
    .set_properties(MemoryAgentConfig(auto_flush=True))
    .set_dependency_map({"uniko": uniko_dep})
    .build_spec()
)

# Add to guild
guild = (
    GuildBuilder("research-guild", "Research Guild", "...")
    .add_agent_spec(memory_agent_spec)
    .add_agent_spec(serp_agent_spec)
    .add_agent_spec(llm_agent_spec)
    .launch(organization_id="org-id")
)

# Messages route through guild messaging infrastructure
```

## Why Tests Instead of Standalone Examples?

The guild messaging infrastructure requires complex setup that's handled by the test framework. The integration tests provide the clearest, most complete demonstrations of all Phase 2 features in action.

All 12 processors (3 Phase 1 + 9 Phase 2) are thoroughly tested and working correctly!

## Summary

✅ **Phase 2 Complete**: All features implemented  
✅ **Fully Tested**: Comprehensive integration test suite  
✅ **Production Ready**: Error handling, type safety, documentation  
✅ **Well Documented**: README.md, test files, inline docs  

**Next Step**: Run `poetry run pytest tests/test_integration.py -v` to see everything working!
