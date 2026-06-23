"""Research workflow example demonstrating Phase 2 features.

This example shows:
1. Creating research goals and tasks
2. Managing task lifecycle
3. Document ingestion
4. Batch observation submission
5. Recalling context for goals

Note: This example uses the test harness for simplicity.
For production use, integrate with the Guild messaging system.
"""

import asyncio
from pathlib import Path
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.guild.dsl import DependencySpec
from rustic_ai.testing.helpers import wrap_agent_for_testing
from rustic_ai.uniko_agent import (
    MemoryAgent,
    MemoryAgentConfig,
    CreateGoalRequest,
    CreateTaskRequest,
    UpdateTaskRequest,
    GetGoalsRequest,
    ObserveTurnRequest,
    IngestDocumentRequest,
    BatchSubmitRequest,
    RecallRequest,
    GoalContextRequest,
    GoalView,
    TaskView,
    GoalsListResponse,
    RecallResponse,
    GoalContext,
)


async def main():
    """Run research workflow example."""

    print("=" * 70)
    print("RESEARCH WORKFLOW EXAMPLE - Phase 2 Features")
    print("=" * 70)

    # Step 1: Build memory agent with test harness
    print("\n🚀 Setting up memory agent...")

    uniko_dep = DependencySpec(
        class_name="rustic_ai.uniko_agent.UnikoResolver",
        properties={
            "storage_path": None,  # In-memory for demo
            "llm_spec": None,
            "streaming": False,
        }
    )

    memory_agent_spec = (
        AgentBuilder(MemoryAgent)
        .set_id("memory_agent")
        .set_name("Research Memory Agent")
        .set_description("Agent for managing research goals and tasks")
        .set_properties(MemoryAgentConfig(auto_flush=True))
        .set_dependency_map({"uniko": uniko_dep})
        .build_spec()
    )

    guild_spec = (
        GuildBuilder("research-guild", "Research Guild", "Research workflow demo")
        .set_execution_engine("rustic_ai.core.guild.execution.sync.sync_exec_engine.SyncExecutionEngine")
        .build_spec()
    )

    # Use test harness for simplicity
    agent, messages = wrap_agent_for_testing(
        agent_spec=memory_agent_spec,
        dependency_map={"uniko": uniko_dep}
    )

    # Create a simple harness wrapper
    class Harness:
        def __init__(self, agent, messages):
            self.agent = agent
            self.messages = messages

        def send_message(self, payload):
            from rustic_ai.core.messaging.core.message import Message, AgentTag
            from rustic_ai.core.utils.gemstone_id import GemstoneGenerator, Priority

            id_gen = GemstoneGenerator(1)
            msg = Message(
                id_obj=id_gen.get_id(Priority.NORMAL),
                sender=AgentTag(id="test", name="test"),
                topics=[self.agent.id],
                format=f"{payload.__class__.__module__}.{payload.__class__.__name__}",
                payload=payload.model_dump(mode="json"),
            )
            msg.topic_published_to = msg.topics[0] if isinstance(msg.topics, list) else msg.topics
            self.agent._on_message(msg)

        def get_sent_messages(self):
            result = list(self.messages)
            self.messages.clear()
            return result

    harness = Harness(agent, messages)
    print("✓ Agent initialized successfully")

    def get_response():
        """Helper to get response payload."""
        responses = harness.get_sent_messages()
        if responses:
            payload = responses[0].payload
            # Check if it's an error
            if isinstance(payload, dict) and payload.get('error'):
                print(f"  ⚠️  Error: {payload.get('message')}")
                return None
            return payload
        return None

    # Step 2: Create research goal
    print("\n📋 Creating research goal...")

    harness.send_message(
        CreateGoalRequest(
            goal_id="rust-research",
            title="Research Rust Memory Safety",
            description="Comprehensive study of Rust's memory safety features",
            metrics={
                "target_sources": 10,
                "target_concepts": 5,
                "depth": "comprehensive"
            },
            guardrails=["Focus on borrow checker", "Include code examples"]
        )
    )

    goal_result = get_response()

    if goal_result and isinstance(goal_result, dict):
        print(f"✓ Created goal: {goal_result.get('title')}")
        print(f"  Goal ID: {goal_result.get('goal_id')}")
        print(f"  Metrics: {goal_result.get('metrics')}")

    # Step 3: Create tasks for the goal
    print("\n📝 Creating research tasks...")

    tasks = [
        ("ownership", "Research ownership system", 1),
        ("borrowing", "Research borrow checker", 1),
        ("lifetimes", "Research lifetime annotations", 2),
        ("examples", "Collect code examples", 3),
    ]

    for task_id, title, priority in tasks:
        harness.send_message(
            CreateTaskRequest(
                goal_id="rust-research",
                task_id=task_id,
                title=title,
                priority=priority
            )
        )

        task_result = get_response()

        if task_result and isinstance(task_result, dict):
            print(f"  ✓ Created task: {task_result.get('title')} (priority: {task_result.get('priority')})")

    # Step 4: Start first task
    print("\n▶️  Starting task 'ownership'...")

    harness.send_message(
        UpdateTaskRequest(
            task_id="ownership",
            action="start"
        )
    )

    update_result = get_response()
    if update_result and isinstance(update_result, dict):
        print(f"  ✓ Task status: {update_result.get('status')}")

    # Step 5: Batch submit research findings
    print("\n💡 Submitting research findings (batch)...")

    findings = [
        {
            "sender_id": "researcher",
            "content": "Rust's ownership system ensures that each value has a single owner at any time",
            "metadata": {"goal_id": "rust-research", "task_id": "ownership", "source": "rust-book"}
        },
        {
            "sender_id": "researcher",
            "content": "The borrow checker validates that references don't outlive their referents",
            "metadata": {"goal_id": "rust-research", "task_id": "ownership", "source": "rust-book"}
        },
        {
            "sender_id": "researcher",
            "content": "Move semantics prevent use-after-free bugs by transferring ownership",
            "metadata": {"goal_id": "rust-research", "task_id": "ownership", "source": "rust-blog"}
        },
    ]

    harness.send_message(
        BatchSubmitRequest(
            turns=findings,
            flush_after=True
        )
    )

    batch_result = get_response()
    if batch_result and isinstance(batch_result, dict):
        print(f"  ✓ Submitted {batch_result.get('submitted_count')} findings")

    # Step 6: Ingest a research document (simulated)
    print("\n📄 Ingesting research document...")

    # Create a temporary markdown document
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("""
# Rust Ownership System

## Key Concepts

1. **Ownership Rules**
   - Each value has exactly one owner
   - When the owner goes out of scope, the value is dropped
   - Ownership can be transferred (moved)

2. **Borrowing**
   - References allow temporary access without ownership
   - Multiple immutable borrows OR one mutable borrow
   - Prevents data races at compile time

3. **Lifetimes**
   - Ensure references are always valid
   - Prevent dangling pointers
   - Often inferred by the compiler
        """)
        doc_path = f.name

    harness.send_message(
        IngestDocumentRequest(
            source_spec={"path": doc_path},
            metadata={"goal_id": "rust-research", "source": "research-notes"}
        )
    )

    ingest_result = get_response()

    if ingest_result and isinstance(ingest_result, dict) and ingest_result.get('success'):
        print(f"  ✓ Ingested document: {ingest_result.get('chunk_count')} chunks extracted")
    elif ingest_result:
        print(f"  ✗ Ingestion failed: {ingest_result.get('error_message')}")

    # Clean up temp file
    Path(doc_path).unlink()

    # Step 7: Recall research findings
    print("\n🔍 Recalling research findings...")

    harness.send_message(
        RecallRequest(
            query="How does Rust prevent memory safety issues?",
            max_tokens=1500
        )
    )

    recall_result = get_response()

    if recall_result and isinstance(recall_result, dict):
        items = recall_result.get('items', [])
        coverage = recall_result.get('coverage', 0)
        print(f"  ✓ Recalled {len(items)} items (coverage: {coverage:.2f})")
        if items:
            print(f"  Top findings:")
            for i, item in enumerate(items[:3], 1):
                kind = item.get('kind', 'Unknown')
                content = item.get('content', '')[:80]
                print(f"    {i}. [{kind}] {content}...")

    # Step 8: Complete the task
    print("\n✅ Completing task 'ownership'...")

    harness.send_message(
        UpdateTaskRequest(
            task_id="ownership",
            action="complete",
            outcome="Documented ownership rules and memory safety guarantees"
        )
    )

    complete_result = get_response()
    if complete_result and isinstance(complete_result, dict):
        print(f"  ✓ Task completed: {complete_result.get('status')}")

    # Step 9: Get goal context
    print("\n📊 Fetching goal context (working memory)...")

    harness.send_message(
        GoalContextRequest(
            goal_id="rust-research",
            include_tasks=True,
            include_episodes=True
        )
    )

    context_result = get_response()

    if context_result and isinstance(context_result, dict):
        goal = context_result.get('goal', {})
        tasks = context_result.get('tasks', [])
        episodes = context_result.get('episodes', [])
        print(f"  ✓ Goal: {goal.get('title')}")
        print(f"  Tasks: {len(tasks)} total")
        for task in tasks:
            print(f"    - {task.get('title')}: {task.get('status')}")
        print(f"  Episodes: {len(episodes)}")

    # Step 10: List all active goals
    print("\n📑 Listing active goals...")

    harness.send_message(
        GetGoalsRequest(phase="active")
    )

    goals_result = get_response()

    if goals_result and isinstance(goals_result, dict):
        total_count = goals_result.get('total_count', 0)
        goals = goals_result.get('goals', [])
        print(f"  ✓ Found {total_count} active goals")
        for goal in goals:
            print(f"    - {goal.get('title')} ({goal.get('goal_id')})")

    # Cleanup
    print("\n🛑 Demo complete...")

    print("\n" + "=" * 70)
    print("✨ Research workflow complete!")
    print("=" * 70)
    print("\nPhase 2 features demonstrated:")
    print("  ✓ Goal creation with metrics and guardrails")
    print("  ✓ Task creation with priorities and dependencies")
    print("  ✓ Task lifecycle (start → complete)")
    print("  ✓ Batch submission of observations")
    print("  ✓ Document ingestion")
    print("  ✓ Goal context retrieval (working memory)")
    print("  ✓ Goal filtering by phase")
    print()


if __name__ == "__main__":
    asyncio.run(main())
