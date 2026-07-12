"""Comprehensive memory agent leveraging uniko's cognitive memory system."""

import logging
from typing import Any, Dict

import uniko
from uniko import IngestSource, RecallSource, Scope, Turn

from rustic_ai.core.guild import agent
from rustic_ai.core.guild.agent import Agent, ProcessContext
from rustic_ai.core.guild.agent_ext.depends.filesystem import FileSystem

from .config import MemoryAgentConfig
from .models import (
    AnswerRequest,
    AnswerResponse,
    BatchSubmitRequest,
    BatchSubmitResponse,
    CreateGoalRequest,
    CreateTaskRequest,
    GetGoalsRequest,
    GoalContext,
    GoalContextRequest,
    GoalsListResponse,
    GoalStatusResponse,
    GoalView,
    IngestDocumentRequest,
    IngestOutcome,
    MemoryAgentError,
    ObserveResult,
    ObserveTurnRequest,
    RecallItem,
    RecallRequest,
    RecallResponse,
    TaskStatusResponse,
    TaskView,
    UpdateGoalRequest,
    UpdateTaskRequest,
)

logger = logging.getLogger(__name__)


class MemoryAgent(Agent[MemoryAgentConfig]):
    """Comprehensive memory agent exposing all uniko capabilities.

    The MemoryAgent provides processors for:
    - Observation ingestion (turns, documents)
    - Knowledge recall and Q&A
    - Goal and task management
    - Advanced queries (Cypher, logic rules)
    - Data access and deletion

    All memory operations are guild-scoped, enabling memory sharing
    across multiple agents in the same guild.
    """

    # ========== Observation Processors ==========

    @agent.processor(ObserveTurnRequest, depends_on=["uniko:guild"])
    async def observe_turn(self, ctx: ProcessContext[ObserveTurnRequest], uniko: uniko.Agent):
        """Observe a conversation turn and extract knowledge.

        Maps incoming message to uniko Turn, observes it, and returns
        extraction results. Auto-creates sessions if needed.

        Args:
            ctx: Process context with ObserveTurnRequest payload
            uniko: Guild-scoped uniko agent (injected dependency)
        """
        req = ctx.payload

        logger.debug(f"Observing turn from sender: {req.sender_id}, content: {req.content}, session_id: {req.session_id}")

        # Determine session ID (fallback to config default or guild_id)
        session_id = req.session_id or self.config.default_session_id or ctx.agent.guild_id

        try:
            # Get or create session
            session = uniko.session(session_id)

            # Build Turn from request
            turn = Turn(req.sender_id, req.content)

            if req.message_id:
                turn = turn.id(req.message_id)
            if req.content_type:
                turn = turn.content_type(req.content_type)
            if req.timestamp:
                turn = turn.at(req.timestamp)
            if req.addressed_to:
                turn = turn.addressed_to(req.addressed_to)
            if req.metadata:
                for k, v in req.metadata.items():
                    turn = turn.metadata(k, v)

            # Handle attachments
            if req.attachments:
                for att in req.attachments:
                    source = self._build_ingest_source(att)
                    turn = turn.attach(source)
            else:
                # Create in-memory markdown from content when no attachments
                source = IngestSource.from_text(req.content).with_mime("text/markdown")
                turn = turn.attach(source)

            # Observe the turn (async)
            result = await session.observe(turn)

            logger.debug(f"Turn observed successfully. Message node ID: {result.message_node_id}")

            # Auto-flush if configured
            if self.config.auto_flush:
                await session.flush()  # @TODO: Bug breaking if auto_flush is true

            # Send response
            ctx.send(
                ObserveResult(
                    message_node_id=result.message_node_id,
                    chunk_node_ids=result.chunk_node_ids,
                    session_node_id=result.session_node_id,
                    sender_node_id=result.sender_node_id,
                    sender_id=result.sender_id,
                    extracted_entities=result.extracted_entities,
                    extracted_observations=result.extracted_observations,
                    attachment_count=result.attachment_count,
                )
            )

        except Exception as e:
            ctx.send(
                MemoryAgentError(
                    error="observation_failed",
                    message=f"Failed to observe turn: {str(e)}",
                    details={"session_id": session_id, "sender_id": req.sender_id},
                )
            )

    # ========== Recall Processors ==========

    @agent.processor(RecallRequest, depends_on=["uniko:guild"])
    async def recall_knowledge(self, ctx: ProcessContext[RecallRequest], uniko: uniko.Agent):
        """Recall knowledge from memory based on query.

        Performs 3-phase cascade recall and returns ranked items with sources.

        Args:
            ctx: Process context with RecallRequest payload
            uniko: Guild-scoped uniko agent (injected dependency)
        """
        req = ctx.payload

        logger.debug(f"Recalling knowledge for query: {req.query} with scope: {req.scope}")

        try:
            # Call recall directly - the API doesn't use RecallConfig anymore
            # The max_tokens, phase restrictions are handled by the uniko library internally
            if req.scope:
                scope = self._build_scope(req.scope)
                bundle = await uniko.recall_in(req.query, scope)
            else:
                bundle = await uniko.recall(req.query)

            # Serialize bundle
            items = [self._serialize_recall_item(item) for item in bundle.items]

            logger.debug(f"Serialized {len(items)} recall items for response.")

            ctx.send(
                RecallResponse(
                    items=items,
                    total_tokens=bundle.total_tokens if hasattr(bundle, "total_tokens") else 0,
                    phase1_only=bundle.phase1_only if hasattr(bundle, "phase1_only") else False,
                    phase2_only=bundle.phase2_only if hasattr(bundle, "phase2_only") else False,
                    coverage=bundle.coverage if hasattr(bundle, "coverage") else 0.0,
                )
            )

        except Exception as e:
            ctx.send(
                MemoryAgentError(
                    error="recall_failed", message=f"Failed to recall knowledge: {str(e)}", details={"query": req.query}
                )
            )

    @agent.processor(AnswerRequest, depends_on=["uniko:guild"])
    async def answer_question(self, ctx: ProcessContext[AnswerRequest], uniko: uniko.Agent):
        """Answer a question using recalled context + LLM.

        Requires LLM configured in UnikoResolver.

        Args:
            ctx: Process context with AnswerRequest payload
            uniko: Guild-scoped uniko agent (injected dependency)
        """
        req = ctx.payload

        try:
            # Generate answer - API doesn't use config parameter anymore
            if req.scope:
                scope = self._build_scope(req.scope)
                answer = await uniko.answer_in(req.question, scope)
            else:
                answer = await uniko.answer(req.question)

            # Serialize context bundle
            context_items = [self._serialize_recall_item(item) for item in answer.context.items]

            context = RecallResponse(
                items=context_items,
                total_tokens=answer.context.total_tokens,
                phase1_only=answer.context.phase1_only,
                phase2_only=answer.context.phase2_only,
                coverage=answer.context.coverage,
            )

            # Serialize citations
            citations = [self._serialize_source(source) for source in answer.citations()]

            ctx.send(
                AnswerResponse(
                    text=answer.text,
                    model=answer.model,
                    input_tokens=answer.input_tokens,
                    output_tokens=answer.output_tokens,
                    recorded_episode=answer.recorded_episode,
                    context=context,
                    citations=citations,
                )
            )

        except Exception as e:
            # Check for LLM configuration error
            error_msg = str(e)
            if (
                "LLM not configured" in error_msg
                or "config error" in error_msg.lower()
                and "requires an LLM" in error_msg
            ):
                ctx.send(
                    MemoryAgentError(
                        error="llm_not_configured",
                        message="LLM not configured in UnikoResolver. Set llm_spec to enable answer generation.",
                        details={"question": req.question},
                    )
                )
            else:
                ctx.send(
                    MemoryAgentError(
                        error="answer_failed",
                        message=f"Failed to generate answer: {error_msg}",
                        details={"question": req.question},
                    )
                )

    # ========== Helper Methods ==========

    def _build_scope(self, spec: Dict[str, Any]) -> Scope:
        """Build Scope from specification dict.

        Args:
            spec: Dict with keys: sessions, participants, since, until

        Returns:
            Scope object
        """
        scope = Scope()

        if "sessions" in spec:
            sessions = spec["sessions"]
            if isinstance(sessions, list):
                scope = scope.sessions(sessions)

        if "participants" in spec:
            participants = spec["participants"]
            if isinstance(participants, list):
                scope = scope.participants(participants)

        if "since" in spec:
            scope = scope.since(spec["since"])

        if "until" in spec:
            scope = scope.until(spec["until"])

        return scope

    def _serialize_recall_item(self, item: "uniko.RecallItem") -> RecallItem:
        """Serialize native RecallItem to Pydantic model.

        Args:
            item: Native RecallItem

        Returns:
            Pydantic RecallItem model
        """
        sources = [self._serialize_source(source) for source in item.sources]

        return RecallItem(
            node_id=item.node_id,
            kind=item.kind,
            score=item.score,
            content=item.content,
            sources=sources,
        )

    def _serialize_source(self, source: RecallSource) -> Dict[str, Any]:
        """Serialize native RecallSource to dict.

        Args:
            source: Native RecallSource

        Returns:
            Dict with source information
        """
        return {
            "kind": source.kind,
            "message_id": source.message_id,
            "artifact_id": source.artifact_id,
            "chunk_id": source.chunk_id,
        }

    def _build_ingest_source(self, spec: Dict[str, Any]) -> IngestSource:
        """Build IngestSource from specification dict.

        Args:
            spec: Dict with keys: path, url, text, bytes, mime_type, metadata

        Returns:
            IngestSource object
        """
        # Determine source type and create base source
        if "path" in spec:
            source = IngestSource.from_path(spec["path"])
        elif "text" in spec:
            source = IngestSource.from_text(spec["text"])
        elif "bytes" in spec:
            source = IngestSource.from_bytes(spec["bytes"])
        else:
            raise ValueError("IngestSource spec must have 'path', 'text', or 'bytes'")

        # Set MIME type if provided
        if "mime_type" in spec:
            source = source.with_mime(spec["mime_type"])

        # Note: metadata attachment not available in current IngestSource API
        # The API uses with_id, with_mime, with_path methods but no metadata method

        return source

    # ========== Document Ingestion Processors (Phase 2) ==========

    @agent.processor(IngestDocumentRequest, depends_on=["uniko:guild", "filesystem:guild_fs:True"])
    async def ingest_document(
        self, ctx: ProcessContext[IngestDocumentRequest], uniko: uniko.Agent, guild_fs: FileSystem
    ):
        """Ingest a document into memory.

        Processes PDFs, HTML, markdown, and other document types.
        Supports files from guild filesystem via MediaLink (on_filesystem=True).

        Args:
            ctx: Process context with IngestDocumentRequest payload
            uniko: Guild-scoped uniko agent (injected dependency)
            guild_fs: Guild filesystem for reading files stored in guild storage
        """
        req = ctx.payload

        logger.debug(
            f"Ingesting document with source spec: {req.source_spec}, media_link: {req.media_link}, session_id: {req.session_id}"
        )

        session_id = req.session_id or self.config.default_session_id or ctx.agent.guild_id

        try:
            session = uniko.session(session_id)

            # Build source from media_link (guild filesystem) or source_spec
            if req.media_link and req.media_link.on_filesystem:
                # Read content from guild filesystem
                file_path = req.media_link.url

                # When guild_fs is configured with asynchronous=True, its sync bridge loop
                # is None by design, so the sync open()/read() raises "Loop is not running".
                # Read via the async API directly instead in that case.
                if getattr(guild_fs, "asynchronous", False):
                    content = await guild_fs._cat_file(file_path)
                else:
                    with guild_fs.open(file_path, "rb") as f:
                        content = f.read()

                # Determine mime type
                mime_type = req.media_link.mimetype or "text/plain"

                # Create IngestSource from bytes
                source = IngestSource.from_bytes(content).with_mime(mime_type)
            elif req.source_spec:
                source = self._build_ingest_source(req.source_spec)
            else:
                raise ValueError("Either media_link or source_spec must be provided")

            # Ingest the document
            outcome = await session.ingest(source)

            logger.debug(
                f"Ingested document with artifact_node_id: {outcome.artifact_node_id},"
                + f"chunk_count: {len(outcome.chunk_node_ids) if outcome.chunk_node_ids else 0},"
                + f"extraction_failed: {outcome.extraction_failed}"
            )

            ctx.send(
                IngestOutcome(
                    artifact_node_id=outcome.artifact_node_id,
                    chunk_count=len(outcome.chunk_node_ids) if outcome.chunk_node_ids else 0,
                    page_count=outcome.page_count if outcome.page_count is not None else 0,
                    extracted_entities=[],  # Not available in current uniko API
                    success=not outcome.extraction_failed,
                )
            )

        except Exception as e:
            logger.exception(f"Failed to ingest document: {e}")
            ctx.send(IngestOutcome(success=False, error_message=f"Failed to ingest document: {str(e)}"))

    @agent.processor(BatchSubmitRequest, depends_on=["uniko:guild"])
    async def batch_submit(self, ctx: ProcessContext[BatchSubmitRequest], uniko: uniko.Agent):
        """Submit multiple turns in batch using streaming mode.

        More efficient than individual observe calls for bulk ingestion.

        Args:
            ctx: Process context with BatchSubmitRequest payload
            uniko: Guild-scoped uniko agent (injected dependency)
        """
        req = ctx.payload

        session_id = req.session_id or self.config.default_session_id or ctx.agent.guild_id

        try:
            session = uniko.session(session_id)
            submitted_count = 0

            # Submit each turn
            for turn_spec in req.turns:
                turn = Turn(turn_spec.get("sender_id"), turn_spec.get("content"))

                if "message_id" in turn_spec:
                    turn = turn.id(turn_spec["message_id"])
                if "content_type" in turn_spec:
                    turn = turn.content_type(turn_spec["content_type"])
                if "metadata" in turn_spec:
                    for k, v in turn_spec["metadata"].items():
                        turn = turn.metadata(k, v)

                await session.submit(turn)
                submitted_count += 1

            # Flush if requested
            flushed = False
            if req.flush_after:
                await session.flush()
                flushed = True

            ctx.send(
                BatchSubmitResponse(
                    submitted_count=submitted_count,
                    flushed=flushed,
                    session_id=session_id,
                )
            )

        except Exception as e:
            ctx.send(
                MemoryAgentError(
                    error="batch_submit_failed",
                    message=f"Failed to submit batch: {str(e)}",
                    details={"session_id": session_id},
                )
            )

    # ========== Goal Management Processors (Phase 2) ==========

    @agent.processor(CreateGoalRequest, depends_on=["uniko:guild"])
    async def create_goal(self, ctx: ProcessContext[CreateGoalRequest], uniko: uniko.Agent):
        """Create a new goal and track it in memory.

        Goals provide high-level objectives for research workflows.

        Args:
            ctx: Process context with CreateGoalRequest payload
            uniko: Guild-scoped uniko agent (injected dependency)
        """
        req = ctx.payload

        try:
            goals = uniko.goals

            # Create the goal
            node_id = await goals.create(
                req.title,
                goal_id=req.goal_id,
                description=req.description,
                status=req.status,
                metrics=req.metrics,
                guardrails=req.guardrails,
                deadline=req.deadline,
                parent_goal_id=req.parent_goal_id,
            )

            # Fetch created goal to return full view
            goal_id = req.goal_id or f"goal-{node_id}"
            goal = await goals.get(goal_id)

            if goal:
                ctx.send(self._serialize_goal_view(goal))
            else:
                # Fallback response
                ctx.send(
                    GoalView(
                        goal_id=goal_id,
                        node_id=node_id,
                        title=req.title,
                        description=req.description,
                        status=req.status,
                    )
                )

        except Exception as e:
            ctx.send(
                MemoryAgentError(
                    error="create_goal_failed", message=f"Failed to create goal: {str(e)}", details={"title": req.title}
                )
            )

    @agent.processor(UpdateGoalRequest, depends_on=["uniko:guild"])
    async def update_goal(self, ctx: ProcessContext[UpdateGoalRequest], uniko: uniko.Agent):
        """Update a goal's status.

        Actions: start, complete, abandon, pause, resume

        Args:
            ctx: Process context with UpdateGoalRequest payload
            uniko: Guild-scoped uniko agent (injected dependency)
        """
        req = ctx.payload

        try:
            goals = uniko.goals

            # Execute action based on type
            if req.action == "start":
                await goals.start(req.goal_id)
            elif req.action == "complete":
                await goals.complete(req.goal_id, result=req.outcome)
            elif req.action == "abandon":
                await goals.abandon(req.goal_id)
            elif req.action == "pause":
                # Check if pause method exists
                if hasattr(goals, "pause"):
                    await goals.pause(req.goal_id)
                else:
                    raise ValueError("pause action not supported by current uniko version")
            elif req.action == "resume":
                # Check if resume method exists
                if hasattr(goals, "resume"):
                    await goals.resume(req.goal_id)
                else:
                    raise ValueError("resume action not supported by current uniko version")
            else:
                raise ValueError(f"Unknown action: {req.action}")

            # Get updated goal to return status
            goal = await goals.get(req.goal_id)
            status = goal.status if goal else req.action

            ctx.send(
                GoalStatusResponse(
                    goal_id=req.goal_id,
                    status=status,
                    updated=True,
                )
            )

        except Exception as e:
            ctx.send(
                MemoryAgentError(
                    error="update_goal_failed",
                    message=f"Failed to update goal: {str(e)}",
                    details={"goal_id": req.goal_id, "action": req.action},
                )
            )

    @agent.processor(GetGoalsRequest, depends_on=["uniko:guild"])
    async def get_goals(self, ctx: ProcessContext[GetGoalsRequest], uniko: uniko.Agent):
        """Get goals by phase.

        Phases: all, active, completed, abandoned

        Args:
            ctx: Process context with GetGoalsRequest payload
            uniko: Guild-scoped uniko agent (injected dependency)
        """
        req = ctx.payload

        try:
            goals_handle = uniko.goals

            # Fetch goals based on phase
            if req.phase == "active":
                goal_list = await goals_handle.active()
            elif req.phase == "completed":
                goal_list = await goals_handle.completed()
            elif req.phase == "abandoned":
                goal_list = await goals_handle.in_phase("abandoned")
            else:  # "all"
                goal_list = await goals_handle.all()

            # Filter by parent if specified
            if req.parent_goal_id:
                goal_list = [g for g in goal_list if getattr(g, "parent_goal_id", None) == req.parent_goal_id]

            # Apply limit
            if req.limit:
                goal_list = goal_list[: req.limit]

            # Serialize goals
            goals = [self._serialize_goal_view(g) for g in goal_list]

            ctx.send(
                GoalsListResponse(
                    goals=goals,
                    total_count=len(goals),
                    phase=req.phase,
                )
            )

        except Exception as e:
            ctx.send(
                MemoryAgentError(
                    error="get_goals_failed", message=f"Failed to get goals: {str(e)}", details={"phase": req.phase}
                )
            )

    # ========== Task Management Processors (Phase 2) ==========

    @agent.processor(CreateTaskRequest, depends_on=["uniko:guild"])
    async def create_task(self, ctx: ProcessContext[CreateTaskRequest], uniko: uniko.Agent):
        """Create a task for a goal.

        Tasks are concrete steps toward achieving a goal.

        Args:
            ctx: Process context with CreateTaskRequest payload
            uniko: Guild-scoped uniko agent (injected dependency)
        """
        req = ctx.payload

        try:
            goals = uniko.goals

            # Create the task - new API: title is first positional, goal_id is keyword
            node_id = await goals.create_task(
                req.title,
                task_id=req.task_id,
                description=req.description,
                priority=req.priority,
                goal_id=req.goal_id,
                depends_on_task_id=req.depends_on[0] if req.depends_on else None,  # API only supports single dependency
            )

            # Return task view (uniko doesn't have get_task, so we construct from request)
            task_id = req.task_id or f"task-{node_id}"
            ctx.send(
                TaskView(
                    task_id=task_id,
                    node_id=node_id,
                    goal_id=req.goal_id,
                    title=req.title,
                    description=req.description,
                    status="pending",
                    priority=req.priority or 3,
                )
            )

        except Exception as e:
            ctx.send(
                MemoryAgentError(
                    error="create_task_failed",
                    message=f"Failed to create task: {str(e)}",
                    details={"goal_id": req.goal_id, "title": req.title},
                )
            )

    @agent.processor(UpdateTaskRequest, depends_on=["uniko:guild"])
    async def update_task(self, ctx: ProcessContext[UpdateTaskRequest], uniko: uniko.Agent):
        """Update a task's status.

        Actions: start, complete, abandon, block, unblock

        Args:
            ctx: Process context with UpdateTaskRequest payload
            uniko: Guild-scoped uniko agent (injected dependency)
        """
        req = ctx.payload

        try:
            goals = uniko.goals

            # Execute action
            if req.action == "start":
                await goals.start_task(req.task_id)
            elif req.action == "complete":
                await goals.complete_task(req.task_id)
            elif req.action == "abandon":
                # Use set_task_status for abandon
                await goals.set_task_status(req.task_id, "abandoned")
            elif req.action == "block":
                await goals.block_task(req.task_id)
            elif req.action == "unblock":
                # Use set_task_status to unblock
                await goals.set_task_status(req.task_id, "pending")
            else:
                raise ValueError(f"Unknown action: {req.action}")

            # Return status (uniko doesn't have get_task)
            status_map = {
                "start": "in_progress",
                "complete": "completed",
                "abandon": "abandoned",
                "block": "blocked",
                "unblock": "pending",
            }
            status = status_map.get(req.action, req.action)

            ctx.send(
                TaskStatusResponse(
                    task_id=req.task_id,
                    status=status,
                    updated=True,
                )
            )

        except Exception as e:
            ctx.send(
                MemoryAgentError(
                    error="update_task_failed",
                    message=f"Failed to update task: {str(e)}",
                    details={"task_id": req.task_id, "action": req.action},
                )
            )

    @agent.processor(GoalContextRequest, depends_on=["uniko:guild"])
    async def get_goal_context(self, ctx: ProcessContext[GoalContextRequest], uniko: uniko.Agent):
        """Get goal working memory context.

        Includes goal, tasks, episodes, and progress metrics.

        Args:
            ctx: Process context with GoalContextRequest payload
            uniko: Guild-scoped uniko agent (injected dependency)
        """
        req = ctx.payload

        try:
            goals = uniko.goals

            # Get goal context (native API keys context on goal_id only)
            context = await goals.context(req.goal_id)

            if context is None:
                raise ValueError(f"Goal context not found: {req.goal_id}")

            # Serialize context
            goal_view = self._serialize_goal_view(context.goal)
            tasks = [self._serialize_task_view(t) for t in context.tasks] if req.include_tasks else []
            episodes = (
                [{"message_id": message_id} for message_id in context.recent_messages]
                if req.include_episodes
                else []
            )

            ctx.send(
                GoalContext(
                    goal=goal_view,
                    tasks=tasks,
                    episodes=episodes,
                    progress={"facts": context.facts, "entities": context.entities, "sessions": context.sessions},
                )
            )

        except Exception as e:
            ctx.send(
                MemoryAgentError(
                    error="get_goal_context_failed",
                    message=f"Failed to get goal context: {str(e)}",
                    details={"goal_id": req.goal_id},
                )
            )

    # ========== Additional Helper Methods ==========

    def _serialize_goal_view(self, goal) -> GoalView:
        """Serialize native goal to GoalView model."""
        return GoalView(
            goal_id=goal.goal_id,
            node_id=None,  # uniko GoalView doesn't have node_id
            title=goal.title,
            description=getattr(goal, "description", None),
            status=goal.status,
            created_at=getattr(goal, "created_at", None),
            updated_at=getattr(goal, "completed_at", None),  # uniko uses completed_at, not updated_at
            metrics=getattr(goal, "metrics", None),
            guardrails=None,  # Not available in uniko GoalView
            deadline=getattr(goal, "deadline", None),
        )

    def _serialize_task_view(self, task) -> TaskView:
        """Serialize native task to TaskView model."""
        return TaskView(
            task_id=task.task_id,
            node_id=None,  # uniko TaskView doesn't have node_id
            goal_id=task.goal_id,
            title=task.title,
            description=getattr(task, "description", None),
            status=task.status,
            priority=getattr(task, "priority", 3),
            created_at=getattr(task, "created_at", None),
        )
