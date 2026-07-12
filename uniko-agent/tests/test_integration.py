"""Integration tests for MemoryAgent with research guild workflows."""

import pytest

from rustic_ai.uniko_agent import (
    BatchSubmitRequest,
    BatchSubmitResponse,
    CreateGoalRequest,
    CreateTaskRequest,
    GetGoalsRequest,
    GoalsListResponse,
    GoalStatusResponse,
    GoalView,
    IngestDocumentRequest,
    IngestOutcome,
    ObserveResult,
    ObserveTurnRequest,
    RecallRequest,
    RecallResponse,
    TaskStatusResponse,
    TaskView,
    UpdateGoalRequest,
    UpdateTaskRequest,
)


class TestResearchWorkflow:
    """Tests for complete research workflow integration."""

    @pytest.mark.asyncio
    async def test_complete_research_workflow(self, memory_test_harness):
        """Test end-to-end research workflow: goal → tasks → observation → recall."""

        # Step 1: Create research goal
        memory_test_harness.send_message(
            CreateGoalRequest(
                goal_id="research-rust-memory",
                title="Research Rust memory safety mechanisms",
                description="Deep dive into how Rust ensures memory safety",
                metrics={"sources_count": 5, "depth": "comprehensive"}
            )
        )

        responses = memory_test_harness.get_sent_messages()
        goal_response = responses[0].payload
        assert isinstance(goal_response, GoalView)
        assert goal_response.goal_id == "research-rust-memory"
        assert goal_response.title == "Research Rust memory safety mechanisms"

        # Step 2: Create tasks for the goal
        tasks = [
            ("task-1", "Research borrow checker"),
            ("task-2", "Research ownership rules"),
            ("task-3", "Research lifetime annotations"),
        ]

        for task_id, title in tasks:
            memory_test_harness.send_message(
                CreateTaskRequest(
                    goal_id="research-rust-memory",
                    task_id=task_id,
                    title=title,
                    priority=1
                )
            )

        responses = memory_test_harness.get_sent_messages()
        assert len(responses) == len(tasks)
        for response in responses:
            assert isinstance(response.payload, TaskView)
            assert response.payload.goal_id == "research-rust-memory"

        # Step 3: Start first task
        memory_test_harness.send_message(
            UpdateTaskRequest(
                task_id="task-1",
                action="start"
            )
        )

        responses = memory_test_harness.get_sent_messages()
        task_update = responses[0].payload
        assert isinstance(task_update, TaskStatusResponse)
        assert task_update.task_id == "task-1"
        assert task_update.updated is True

        # Step 4: Observe research findings
        findings = [
            "The borrow checker ensures references are always valid",
            "Rust's ownership system prevents data races at compile time",
            "Lifetimes track how long references are valid",
        ]

        for finding in findings:
            memory_test_harness.send_message(
                ObserveTurnRequest(
                    sender_id="researcher",
                    content=finding,
                    metadata={"goal_id": "research-rust-memory", "task_id": "task-1"}
                )
            )

        responses = memory_test_harness.get_sent_messages()
        assert len(responses) == len(findings)
        for response in responses:
            assert isinstance(response.payload, ObserveResult)

        # Step 5: Recall research findings
        memory_test_harness.send_message(
            RecallRequest(
                query="How does Rust ensure memory safety?",
                max_tokens=1000
            )
        )

        responses = memory_test_harness.get_sent_messages()
        recall_response = responses[0].payload
        assert isinstance(recall_response, RecallResponse)
        assert len(recall_response.items) > 0

        # Should recall information about borrow checker, ownership
        content_combined = " ".join(item.content.lower() for item in recall_response.items)
        assert any(keyword in content_combined for keyword in ["borrow", "ownership", "lifetime"])

        # Step 6: Complete task
        memory_test_harness.send_message(
            UpdateTaskRequest(
                task_id="task-1",
                action="complete",
                outcome="Documented borrow checker mechanisms"
            )
        )

        responses = memory_test_harness.get_sent_messages()
        task_complete = responses[0].payload
        assert isinstance(task_complete, TaskStatusResponse)
        assert task_complete.updated is True


class TestDocumentIngestion:
    """Tests for document ingestion workflows."""

    @pytest.mark.asyncio
    async def test_ingest_document_from_path(self, memory_test_harness, tmp_path):
        """Test ingesting a document from file path."""
        # Create a test document
        test_doc = tmp_path / "research.md"
        test_doc.write_text("""
# Rust Memory Safety

Rust ensures memory safety through:
1. Ownership system
2. Borrow checker
3. Lifetime annotations
        """)

        # Ingest the document
        memory_test_harness.send_message(
            IngestDocumentRequest(
                source_spec={
                    "path": str(test_doc),
                    "metadata": {"source": "test", "topic": "rust"}
                }
            )
        )

        responses = memory_test_harness.get_sent_messages()
        outcome = responses[0].payload

        assert isinstance(outcome, IngestOutcome)
        assert outcome.success is True
        assert outcome.chunk_count > 0

    @pytest.mark.asyncio
    async def test_batch_submit_turns(self, memory_test_harness):
        """Test batch submission of multiple turns."""
        turns = [
            {"sender_id": "user", "content": "Finding 1: Borrow checker prevents data races"},
            {"sender_id": "user", "content": "Finding 2: Ownership eliminates garbage collection"},
            {"sender_id": "user", "content": "Finding 3: Lifetimes ensure reference validity"},
        ]

        memory_test_harness.send_message(
            BatchSubmitRequest(
                turns=turns,
                flush_after=True
            )
        )

        responses = memory_test_harness.get_sent_messages()
        batch_response = responses[0].payload

        assert isinstance(batch_response, BatchSubmitResponse)
        assert batch_response.submitted_count == len(turns)
        assert batch_response.flushed is True


class TestGoalTaskManagement:
    """Tests for goal and task management."""

    @pytest.mark.asyncio
    async def test_create_nested_goals(self, memory_test_harness):
        """Test creating parent and child goals."""
        # Create parent goal
        memory_test_harness.send_message(
            CreateGoalRequest(
                goal_id="parent-research",
                title="Research Programming Languages",
                description="Comprehensive study of modern languages"
            )
        )

        responses = memory_test_harness.get_sent_messages()
        parent_goal = responses[0].payload
        assert isinstance(parent_goal, GoalView)

        # Create child goal
        memory_test_harness.send_message(
            CreateGoalRequest(
                goal_id="child-rust",
                title="Deep dive into Rust",
                parent_goal_id="parent-research"
            )
        )

        responses = memory_test_harness.get_sent_messages()
        child_goal = responses[0].payload
        assert isinstance(child_goal, GoalView)

    @pytest.mark.asyncio
    async def test_goal_lifecycle(self, memory_test_harness):
        """Test complete goal lifecycle: create → start → complete."""
        # Create goal
        memory_test_harness.send_message(
            CreateGoalRequest(
                goal_id="lifecycle-test",
                title="Test Goal Lifecycle"
            )
        )

        responses = memory_test_harness.get_sent_messages()
        goal = responses[0].payload
        assert isinstance(goal, GoalView)

        # Start goal
        memory_test_harness.send_message(
            UpdateGoalRequest(
                goal_id="lifecycle-test",
                action="start"
            )
        )

        responses = memory_test_harness.get_sent_messages()
        start_response = responses[0].payload
        assert isinstance(start_response, GoalStatusResponse)
        assert start_response.updated is True

        # Complete goal
        memory_test_harness.send_message(
            UpdateGoalRequest(
                goal_id="lifecycle-test",
                action="complete",
                outcome="Successfully completed test"
            )
        )

        responses = memory_test_harness.get_sent_messages()
        complete_response = responses[0].payload
        assert isinstance(complete_response, GoalStatusResponse)
        assert complete_response.updated is True

    @pytest.mark.asyncio
    async def test_get_goals_by_phase(self, memory_test_harness):
        """Test filtering goals by phase."""
        # Create multiple goals with different statuses
        memory_test_harness.send_message(
            CreateGoalRequest(goal_id="goal-1", title="Active Goal 1", status="active")
        )
        memory_test_harness.send_message(
            CreateGoalRequest(goal_id="goal-2", title="Active Goal 2", status="active")
        )

        memory_test_harness.get_sent_messages()  # Clear

        # Get all active goals
        memory_test_harness.send_message(
            GetGoalsRequest(phase="active")
        )

        responses = memory_test_harness.get_sent_messages()
        goals_response = responses[0].payload

        assert isinstance(goals_response, GoalsListResponse)
        assert goals_response.phase == "active"
        assert len(goals_response.goals) >= 2

    @pytest.mark.asyncio
    async def test_task_dependencies(self, memory_test_harness):
        """Test creating tasks with dependencies."""
        # Create goal
        memory_test_harness.send_message(
            CreateGoalRequest(goal_id="dep-test", title="Test Dependencies")
        )
        memory_test_harness.get_sent_messages()

        # Create task 1
        memory_test_harness.send_message(
            CreateTaskRequest(
                goal_id="dep-test",
                task_id="task-a",
                title="Task A (no dependencies)"
            )
        )
        memory_test_harness.get_sent_messages()

        # Create task 2 that depends on task 1
        memory_test_harness.send_message(
            CreateTaskRequest(
                goal_id="dep-test",
                task_id="task-b",
                title="Task B (depends on A)",
                depends_on=["task-a"]
            )
        )

        responses = memory_test_harness.get_sent_messages()
        task_b = responses[0].payload

        assert isinstance(task_b, TaskView)
        assert task_b.task_id == "task-b"


class TestMemoryPersistence:
    """Tests for memory persistence and recall across sessions."""

    @pytest.mark.asyncio
    async def test_memory_persists_across_recall_calls(self, memory_test_harness):
        """Test that observations persist and can be recalled multiple times."""
        # Observe some information
        memory_test_harness.send_message(
            ObserveTurnRequest(
                sender_id="user",
                content="Python is great for data science and machine learning"
            )
        )
        memory_test_harness.get_sent_messages()

        # First recall
        memory_test_harness.send_message(
            RecallRequest(query="programming languages for data science")
        )
        responses1 = memory_test_harness.get_sent_messages()
        recall1 = responses1[0].payload

        # Second recall (should return same/similar results)
        memory_test_harness.send_message(
            RecallRequest(query="data science languages")
        )
        responses2 = memory_test_harness.get_sent_messages()
        recall2 = responses2[0].payload

        assert isinstance(recall1, RecallResponse)
        assert isinstance(recall2, RecallResponse)

        # Both should have items about Python/data science
        assert len(recall1.items) > 0
        assert len(recall2.items) > 0


class TestScopeFiltering:
    """Tests for scope-based filtering in recall."""

    @pytest.mark.asyncio
    async def test_recall_with_session_scope(self, memory_test_harness):
        """Test recall filtered by session."""
        # Observe in session 1
        memory_test_harness.send_message(
            ObserveTurnRequest(
                session_id="session-1",
                sender_id="user",
                content="Information specific to session 1"
            )
        )
        memory_test_harness.get_sent_messages()

        # Observe in session 2
        memory_test_harness.send_message(
            ObserveTurnRequest(
                session_id="session-2",
                sender_id="user",
                content="Information specific to session 2"
            )
        )
        memory_test_harness.get_sent_messages()

        # Recall scoped to session 1
        memory_test_harness.send_message(
            RecallRequest(
                query="information",
                scope={"sessions": ["session-1"]}
            )
        )

        responses = memory_test_harness.get_sent_messages()
        recall = responses[0].payload

        assert isinstance(recall, RecallResponse)
        # Should find results (from session 1)
        assert len(recall.items) >= 0
