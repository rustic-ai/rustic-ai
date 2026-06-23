"""Comprehensive memory agent leveraging uniko's cognitive memory system."""

import uniko
from typing import Dict, Any
from rustic_ai.core.guild.agent import Agent
from rustic_ai.core.guild.agent import ProcessContext
from rustic_ai.core.guild import agent

from .config import MemoryAgentConfig
from .models import (
    ObserveTurnRequest, ObserveResult,
    RecallRequest, RecallResponse, RecallItem,
    AnswerRequest, AnswerResponse,
    IngestDocumentRequest, IngestOutcome,
    BatchSubmitRequest, BatchSubmitResponse,
    CreateGoalRequest, GoalView, UpdateGoalRequest, GoalStatusResponse,
    GetGoalsRequest, GoalsListResponse,
    CreateTaskRequest, TaskView, UpdateTaskRequest, TaskStatusResponse,
    GoalContextRequest, GoalContext,
    MemoryAgentError
)


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
    async def observe_turn(
        self,
        ctx: ProcessContext[ObserveTurnRequest],
        uniko: uniko.Agent
    ):
        """Observe a conversation turn and extract knowledge.

        Maps incoming message to uniko Turn, observes it, and returns
        extraction results. Auto-creates sessions if needed.

        Args:
            ctx: Process context with ObserveTurnRequest payload
            uniko_agent: Guild-scoped uniko agent (injected dependency)
        """
        req = ctx.payload

        # Determine session ID (fallback to config default or guild_id)
        session_id = (
            req.session_id
            or self.config.default_session_id
            or ctx.agent.guild_id
        )

        try:
            # Get or create session
            session = uniko.session(session_id)

            # Build Turn from request
            turn = uniko.Turn(req.sender_id, req.content)

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

            # Observe the turn (async)
            result = await session.observe(turn)

            # Auto-flush if configured
            if self.config.auto_flush:
                await session.flush()

            # Send response
            ctx.send(ObserveResult(
                message_node_id=result.message_node_id,
                chunk_node_ids=result.chunk_node_ids,
                session_node_id=result.session_node_id,
                sender_node_id=result.sender_node_id,
                sender_id=result.sender_id,
                extracted_entities=result.extracted_entities,
                extracted_observations=result.extracted_observations,
                attachment_count=result.attachment_count,
            ))

        except Exception as e:
            ctx.send(MemoryAgentError(
                error="observation_failed",
                message=f"Failed to observe turn: {str(e)}",
                details={"session_id": session_id, "sender_id": req.sender_id}
            ))

    # ========== Recall Processors ==========

    @agent.processor(RecallRequest, depends_on=["uniko:guild"])
    async def recall_knowledge(
        self,
        ctx: ProcessContext[RecallRequest],
        uniko: uniko.Agent
    ):
        """Recall knowledge from memory based on query.

        Performs 3-phase cascade recall and returns ranked items with sources.

        Args:
            ctx: Process context with RecallRequest payload
            uniko_agent: Guild-scoped uniko agent (injected dependency)
        """
        req = ctx.payload

        try:
            # Build RecallConfig
            config = uniko.RecallConfig()

            # Set max tokens (from request or agent config)
            max_tokens = req.max_tokens or self.config.recall_max_tokens
            config = config.max_tokens(max_tokens)

            # Set phase restrictions
            if req.phase1_only or self.config.recall_phase1_only:
                config = config.phase1_only()
            elif req.phase2_only:
                config = config.phase2_only()

            # Build scope if provided
            if req.scope:
                scope = self._build_scope(req.scope)
                bundle = await uniko.recall_in(req.query, scope, config)
            else:
                bundle = await uniko.recall(req.query, config)

            # Serialize bundle
            items = [self._serialize_recall_item(item) for item in bundle.items]

            ctx.send(RecallResponse(
                items=items,
                total_tokens=bundle.total_tokens,
                phase1_only=bundle.phase1_only,
                phase2_only=bundle.phase2_only,
                coverage=bundle.coverage,
            ))

        except Exception as e:
            ctx.send(MemoryAgentError(
                error="recall_failed",
                message=f"Failed to recall knowledge: {str(e)}",
                details={"query": req.query}
            ))

    @agent.processor(AnswerRequest, depends_on=["uniko:guild"])
    async def answer_question(
        self,
        ctx: ProcessContext[AnswerRequest],
        uniko: uniko.Agent
    ):
        """Answer a question using recalled context + LLM.

        Requires LLM configured in UnikoResolver.

        Args:
            ctx: Process context with AnswerRequest payload
            uniko_agent: Guild-scoped uniko agent (injected dependency)
        """
        req = ctx.payload

        try:
            # Build RecallConfig
            max_tokens = req.max_tokens or self.config.answer_max_tokens
            config = uniko.RecallConfig().max_tokens(max_tokens)

            # Generate answer
            if req.scope:
                scope = self._build_scope(req.scope)
                answer = await uniko.answer_in(req.question, scope, config)
            else:
                answer = await uniko.answer(req.question, config)

            # Serialize context bundle
            context_items = [
                self._serialize_recall_item(item)
                for item in answer.context.items
            ]

            context = RecallResponse(
                items=context_items,
                total_tokens=answer.context.total_tokens,
                phase1_only=answer.context.phase1_only,
                phase2_only=answer.context.phase2_only,
                coverage=answer.context.coverage,
            )

            # Serialize citations
            citations = [
                self._serialize_source(source)
                for source in answer.citations()
            ]

            ctx.send(AnswerResponse(
                text=answer.text,
                model=answer.model,
                input_tokens=answer.input_tokens,
                output_tokens=answer.output_tokens,
                recorded_episode=answer.recorded_episode,
                context=context,
                citations=citations,
            ))

        except Exception as e:
            # Check for LLM configuration error
            error_msg = str(e)
            if "LLM not configured" in error_msg or "ConfigError" in error_msg:
                ctx.send(MemoryAgentError(
                    error="llm_not_configured",
                    message="LLM not configured in UnikoResolver. Set llm_spec to enable answer generation.",
                    details={"question": req.question}
                ))
            else:
                ctx.send(MemoryAgentError(
                    error="answer_failed",
                    message=f"Failed to generate answer: {error_msg}",
                    details={"question": req.question}
                ))

    # ========== Helper Methods ==========

    def _build_scope(self, spec: Dict[str, Any]) -> uniko.Scope:
        """Build uniko.Scope from specification dict.

        Args:
            spec: Dict with keys: sessions, participants, since, until

        Returns:
            uniko.Scope object
        """
        scope = uniko.Scope()

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

    def _serialize_recall_item(self, item: uniko.RecallItem) -> RecallItem:
        """Serialize native RecallItem to Pydantic model.

        Args:
            item: Native uniko.RecallItem

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

    def _serialize_source(self, source: uniko.RecallSource) -> Dict[str, Any]:
        """Serialize native RecallSource to dict.

        Args:
            source: Native uniko.RecallSource

        Returns:
            Dict with source information
        """
        return {
            "kind": source.kind,
            "message_id": source.message_id,
            "artifact_id": source.artifact_id,
            "chunk_id": source.chunk_id,
        }

    def _build_ingest_source(self, spec: Dict[str, Any]) -> uniko.IngestSource:
        """Build uniko.IngestSource from specification dict.

        Args:
            spec: Dict with keys: path, url, mime_type, metadata

        Returns:
            uniko.IngestSource object
        """
        # Determine source type
        if "path" in spec:
            source = uniko.IngestSource.path(spec["path"])
        elif "url" in spec:
            source = uniko.IngestSource.url(spec["url"])
        elif "bytes" in spec:
            mime_type = spec.get("mime_type", "application/octet-stream")
            source = uniko.IngestSource.bytes(spec["bytes"], mime_type)
        else:
            raise ValueError("IngestSource spec must have 'path', 'url', or 'bytes'")

        # Add metadata if provided
        if "metadata" in spec:
            for k, v in spec["metadata"].items():
                source = source.metadata(k, v)

        return source

    # ========== Document Ingestion Processors (Phase 2) ==========

    @agent.processor(IngestDocumentRequest, depends_on=["uniko:guild"])
    async def ingest_document(
        self,
        ctx: ProcessContext[IngestDocumentRequest],
        uniko: uniko.Agent
    ):
        """Ingest a document into memory.

        Processes PDFs, HTML, markdown, and other document types.

        Args:
            ctx: Process context with IngestDocumentRequest payload
            uniko_agent: Guild-scoped uniko agent (injected dependency)
        """
        req = ctx.payload

        session_id = (
            req.session_id
            or self.config.default_session_id
            or ctx.agent.guild_id
        )

        try:
            session = uniko.session(session_id)
            source = self._build_ingest_source(req.source_spec)

            # Ingest the document
            outcome = await session.ingest(source)

            ctx.send(IngestOutcome(
                artifact_node_id=outcome.artifact_node_id,
                chunk_count=outcome.chunk_count,
                page_count=outcome.page_count,
                extracted_entities=outcome.extracted_entities,
                success=True,
            ))

        except Exception as e:
            ctx.send(IngestOutcome(
                success=False,
                error_message=f"Failed to ingest document: {str(e)}"
            ))

    @agent.processor(BatchSubmitRequest, depends_on=["uniko:guild"])
    async def batch_submit(
        self,
        ctx: ProcessContext[BatchSubmitRequest],
        uniko: uniko.Agent
    ):
        """Submit multiple turns in batch using streaming mode.

        More efficient than individual observe calls for bulk ingestion.

        Args:
            ctx: Process context with BatchSubmitRequest payload
            uniko_agent: Guild-scoped uniko agent (injected dependency)
        """
        req = ctx.payload

        session_id = (
            req.session_id
            or self.config.default_session_id
            or ctx.agent.guild_id
        )

        try:
            session = uniko.session(session_id)
            submitted_count = 0

            # Submit each turn
            for turn_spec in req.turns:
                turn = uniko.Turn(
                    turn_spec.get("sender_id"),
                    turn_spec.get("content")
                )

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

            ctx.send(BatchSubmitResponse(
                submitted_count=submitted_count,
                flushed=flushed,
                session_id=session_id,
            ))

        except Exception as e:
            ctx.send(MemoryAgentError(
                error="batch_submit_failed",
                message=f"Failed to submit batch: {str(e)}",
                details={"session_id": session_id}
            ))

    # ========== Goal Management Processors (Phase 2) ==========

    @agent.processor(CreateGoalRequest, depends_on=["uniko:guild"])
    async def create_goal(
        self,
        ctx: ProcessContext[CreateGoalRequest],
        uniko: uniko.Agent
    ):
        """Create a new goal and track it in memory.

        Goals provide high-level objectives for research workflows.

        Args:
            ctx: Process context with CreateGoalRequest payload
            uniko_agent: Guild-scoped uniko agent (injected dependency)
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
                ctx.send(GoalView(
                    goal_id=goal_id,
                    node_id=node_id,
                    title=req.title,
                    description=req.description,
                    status=req.status,
                ))

        except Exception as e:
            ctx.send(MemoryAgentError(
                error="create_goal_failed",
                message=f"Failed to create goal: {str(e)}",
                details={"title": req.title}
            ))

    @agent.processor(UpdateGoalRequest, depends_on=["uniko:guild"])
    async def update_goal(
        self,
        ctx: ProcessContext[UpdateGoalRequest],
        uniko: uniko.Agent
    ):
        """Update a goal's status.

        Actions: start, complete, abandon, pause, resume

        Args:
            ctx: Process context with UpdateGoalRequest payload
            uniko_agent: Guild-scoped uniko agent (injected dependency)
        """
        req = ctx.payload

        try:
            goals = uniko.goals

            # Execute action based on type
            if req.action == "start":
                await goals.start(req.goal_id)
            elif req.action == "complete":
                await goals.complete(req.goal_id, outcome=req.outcome)
            elif req.action == "abandon":
                await goals.abandon(req.goal_id, reason=req.outcome)
            elif req.action == "pause":
                await goals.pause(req.goal_id)
            elif req.action == "resume":
                await goals.resume(req.goal_id)
            else:
                raise ValueError(f"Unknown action: {req.action}")

            # Get updated goal to return status
            goal = await goals.get(req.goal_id)
            status = goal.status if goal else req.action

            ctx.send(GoalStatusResponse(
                goal_id=req.goal_id,
                status=status,
                updated=True,
            ))

        except Exception as e:
            ctx.send(MemoryAgentError(
                error="update_goal_failed",
                message=f"Failed to update goal: {str(e)}",
                details={"goal_id": req.goal_id, "action": req.action}
            ))

    @agent.processor(GetGoalsRequest, depends_on=["uniko:guild"])
    async def get_goals(
        self,
        ctx: ProcessContext[GetGoalsRequest],
        uniko: uniko.Agent
    ):
        """Get goals by phase.

        Phases: all, active, completed, abandoned

        Args:
            ctx: Process context with GetGoalsRequest payload
            uniko_agent: Guild-scoped uniko agent (injected dependency)
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
                goal_list = await goals_handle.abandoned()
            else:  # "all"
                goal_list = await goals_handle.all()

            # Filter by parent if specified
            if req.parent_goal_id:
                goal_list = [g for g in goal_list if getattr(g, "parent_goal_id", None) == req.parent_goal_id]

            # Apply limit
            if req.limit:
                goal_list = goal_list[:req.limit]

            # Serialize goals
            goals = [self._serialize_goal_view(g) for g in goal_list]

            ctx.send(GoalsListResponse(
                goals=goals,
                total_count=len(goals),
                phase=req.phase,
            ))

        except Exception as e:
            ctx.send(MemoryAgentError(
                error="get_goals_failed",
                message=f"Failed to get goals: {str(e)}",
                details={"phase": req.phase}
            ))

    # ========== Task Management Processors (Phase 2) ==========

    @agent.processor(CreateTaskRequest, depends_on=["uniko:guild"])
    async def create_task(
        self,
        ctx: ProcessContext[CreateTaskRequest],
        uniko: uniko.Agent
    ):
        """Create a task for a goal.

        Tasks are concrete steps toward achieving a goal.

        Args:
            ctx: Process context with CreateTaskRequest payload
            uniko_agent: Guild-scoped uniko agent (injected dependency)
        """
        req = ctx.payload

        try:
            goals = uniko.goals

            # Create the task
            node_id = await goals.create_task(
                req.goal_id,
                req.title,
                task_id=req.task_id,
                description=req.description,
                priority=req.priority,
                depends_on=req.depends_on,
            )

            # Fetch created task
            task_id = req.task_id or f"task-{node_id}"
            task = await goals.get_task(task_id)

            if task:
                ctx.send(self._serialize_task_view(task))
            else:
                # Fallback response
                ctx.send(TaskView(
                    task_id=task_id,
                    node_id=node_id,
                    goal_id=req.goal_id,
                    title=req.title,
                    description=req.description,
                    status="pending",
                    priority=req.priority,
                ))

        except Exception as e:
            ctx.send(MemoryAgentError(
                error="create_task_failed",
                message=f"Failed to create task: {str(e)}",
                details={"goal_id": req.goal_id, "title": req.title}
            ))

    @agent.processor(UpdateTaskRequest, depends_on=["uniko:guild"])
    async def update_task(
        self,
        ctx: ProcessContext[UpdateTaskRequest],
        uniko: uniko.Agent
    ):
        """Update a task's status.

        Actions: start, complete, abandon, block, unblock

        Args:
            ctx: Process context with UpdateTaskRequest payload
            uniko_agent: Guild-scoped uniko agent (injected dependency)
        """
        req = ctx.payload

        try:
            goals = uniko.goals

            # Execute action
            if req.action == "start":
                await goals.start_task(req.task_id)
            elif req.action == "complete":
                await goals.complete_task(req.task_id, outcome=req.outcome)
            elif req.action == "abandon":
                await goals.abandon_task(req.task_id, reason=req.outcome)
            elif req.action == "block":
                await goals.block_task(req.task_id)
            elif req.action == "unblock":
                await goals.unblock_task(req.task_id)
            else:
                raise ValueError(f"Unknown action: {req.action}")

            # Get updated task
            task = await goals.get_task(req.task_id)
            status = task.status if task else req.action

            ctx.send(TaskStatusResponse(
                task_id=req.task_id,
                status=status,
                updated=True,
            ))

        except Exception as e:
            ctx.send(MemoryAgentError(
                error="update_task_failed",
                message=f"Failed to update task: {str(e)}",
                details={"task_id": req.task_id, "action": req.action}
            ))

    @agent.processor(GoalContextRequest, depends_on=["uniko:guild"])
    async def get_goal_context(
        self,
        ctx: ProcessContext[GoalContextRequest],
        uniko: uniko.Agent
    ):
        """Get goal working memory context.

        Includes goal, tasks, episodes, and progress metrics.

        Args:
            ctx: Process context with GoalContextRequest payload
            uniko_agent: Guild-scoped uniko agent (injected dependency)
        """
        req = ctx.payload

        try:
            goals = uniko.goals

            # Get goal context
            context = await goals.context(
                req.goal_id,
                include_tasks=req.include_tasks,
                include_episodes=req.include_episodes,
            )

            # Serialize context
            goal_view = self._serialize_goal_view(context.goal)
            tasks = [self._serialize_task_view(t) for t in context.tasks]
            episodes = [self._serialize_episode(e) for e in context.episodes]

            ctx.send(GoalContext(
                goal=goal_view,
                tasks=tasks,
                episodes=episodes,
                progress=context.progress or {},
            ))

        except Exception as e:
            ctx.send(MemoryAgentError(
                error="get_goal_context_failed",
                message=f"Failed to get goal context: {str(e)}",
                details={"goal_id": req.goal_id}
            ))

    # ========== Additional Helper Methods ==========

    def _serialize_goal_view(self, goal) -> GoalView:
        """Serialize native goal to GoalView model."""
        return GoalView(
            goal_id=goal.goal_id,
            node_id=goal.node_id,
            title=goal.title,
            description=getattr(goal, "description", None),
            status=goal.status,
            created_at=getattr(goal, "created_at", None),
            updated_at=getattr(goal, "updated_at", None),
            metrics=getattr(goal, "metrics", None),
            guardrails=getattr(goal, "guardrails", None),
            deadline=getattr(goal, "deadline", None),
        )

    def _serialize_task_view(self, task) -> TaskView:
        """Serialize native task to TaskView model."""
        return TaskView(
            task_id=task.task_id,
            node_id=task.node_id,
            goal_id=task.goal_id,
            title=task.title,
            description=getattr(task, "description", None),
            status=task.status,
            priority=getattr(task, "priority", 3),
            created_at=getattr(task, "created_at", None),
        )

    def _serialize_episode(self, episode) -> Dict[str, Any]:
        """Serialize native episode to dict."""
        return {
            "episode_id": getattr(episode, "episode_id", None),
            "node_id": getattr(episode, "node_id", None),
            "action_type": getattr(episode, "action_type", None),
            "outcome": getattr(episode, "outcome", None),
            "timestamp": getattr(episode, "timestamp", None),
        }
