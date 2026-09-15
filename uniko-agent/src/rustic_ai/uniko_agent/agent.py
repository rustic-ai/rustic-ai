"""Comprehensive memory agent leveraging uniko's cognitive memory system."""

import asyncio
import logging
from typing import Any, Dict, Optional

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
    DeleteMemorySessionRequest,
    FinalizeMemorySessionRequest,
    FinalizeMemorySessionResult,
    ForgetMemoryParticipantRequest,
    ForgetMemoryRecordRequest,
    GetGoalsRequest,
    GoalContext,
    GoalContextRequest,
    GoalsListResponse,
    GoalStatusResponse,
    GoalView,
    IngestDocumentRequest,
    IngestOutcome,
    MemoryAgentError,
    MemoryDeletionResult,
    MemoryRecordKind,
    ObserveResult,
    ObserveTurnRequest,
    RecallItem,
    RecallRequest,
    RecallResponse,
    RecordMemoryRequest,
    RecordMemoryResult,
    TaskStatusResponse,
    TaskView,
    UpdateGoalRequest,
    UpdateTaskRequest,
)

logger = logging.getLogger(__name__)

_RECORD_PREFIX = "rustic-memory"
_ERROR_MESSAGES = {
    "record_rejected": "The memory record was rejected.",
    "record_failed": "The memory record could not be saved.",
    "recall_failed": "Memory could not be recalled.",
    "document_rejected": "The guild document reference was rejected.",
    "document_ingest_failed": "The guild document could not be saved to memory.",
    "finalize_failed": "The memory session could not be finalized.",
    "forget_failed": "The requested memory could not be forgotten.",
    "observation_failed": "The conversation turn could not be saved to memory.",
    "answer_failed": "Memory could not generate an answer.",
    "llm_not_configured": "Memory answer generation is unavailable.",
    "batch_submit_failed": "The memory batch could not be saved.",
    "create_goal_failed": "The memory goal could not be created.",
    "update_goal_failed": "The memory goal could not be updated.",
    "get_goals_failed": "Memory goals could not be retrieved.",
    "create_task_failed": "The memory task could not be created.",
    "update_task_failed": "The memory task could not be updated.",
    "get_goal_context_failed": "The memory goal context could not be retrieved.",
}


class MemoryAgent(Agent[MemoryAgentConfig]):
    """Private Uniko memory with shared input documents from the guild filesystem."""

    def _session_lock(self, session_id: str) -> asyncio.Lock:
        """Serialize writes, finalization, and recall within one memory scope."""
        locks = getattr(self, "_session_locks", None)
        if locks is None:
            locks = {}
            self._session_locks = locks
        return locks.setdefault(session_id, asyncio.Lock())

    @staticmethod
    def _record_key(kind: MemoryRecordKind, record_id: str) -> str:
        return f"{_RECORD_PREFIX}:{kind.value}:{record_id}"

    @staticmethod
    def _record_text(kind: MemoryRecordKind, record_id: str, sender_id: str, content: str) -> str:
        return f"Memory record type: {kind.value}\n" f"Record ID: {record_id}\n" f"Source: {sender_id}\n\n" f"{content}"

    @staticmethod
    def _record_envelope(content: str) -> tuple[Optional[MemoryRecordKind], Optional[str], str]:
        marker = "Memory record type: "
        marker_index = content.find(marker)
        if marker_index < 0 or marker_index > 512:
            return None, None, content
        envelope, separator, body = content[marker_index:].partition("\n\n")
        if not separator:
            return None, None, content
        fields = {}
        for line in envelope.splitlines():
            key, delimiter, value = line.partition(": ")
            if delimiter:
                fields[key] = value
        try:
            kind = MemoryRecordKind(fields["Memory record type"])
        except (KeyError, ValueError):
            return None, None, content
        return kind, fields.get("Record ID"), body.strip()

    @staticmethod
    def _record_kind(value: Optional[str]) -> Optional[MemoryRecordKind]:
        if not value:
            return None
        marker = f"{_RECORD_PREFIX}:"
        if marker not in value:
            return None
        suffix = value.split(marker, 1)[1]
        raw_kind = suffix.split(":", 1)[0]
        try:
            return MemoryRecordKind(raw_kind)
        except ValueError:
            return None

    def _send_failure(self, ctx: ProcessContext, code: str) -> None:
        ctx.send_error(MemoryAgentError(error=code, message=_ERROR_MESSAGES[code]))

    def _producer_is_allowed(self, ctx: ProcessContext, kind: MemoryRecordKind) -> bool:
        allowed = self.config.allowed_record_producers.get(kind.value)
        return allowed is None or ctx.message.sender.id in allowed

    @staticmethod
    def _deletion_result(report: Any) -> MemoryDeletionResult:
        return MemoryDeletionResult(
            nodes_redacted=int(getattr(report, "nodes_redacted", 0)),
            nodes_deleted=int(getattr(report, "nodes_deleted", 0)),
            edges_deleted=int(getattr(report, "edges_deleted", 0)),
            facts_invalidated=int(getattr(report, "facts_invalidated", 0)),
            root_existed=bool(getattr(report, "root_existed", False)),
        )

    @agent.processor(RecordMemoryRequest, depends_on=["uniko"])
    async def record_memory(self, ctx: ProcessContext[RecordMemoryRequest], uniko: uniko.Agent):
        """Persist a typed record without allowing callers to choose host storage."""
        req = ctx.payload
        if not self._producer_is_allowed(ctx, req.kind):
            self._send_failure(ctx, "record_rejected")
            return

        key = self._record_key(req.kind, req.record_id)
        try:
            async with self._session_lock(req.session_id):
                session = uniko.session(req.session_id)
                if req.kind in {MemoryRecordKind.USER_ASSERTION, MemoryRecordKind.ASSISTANT_RESPONSE}:
                    role = "user" if req.kind == MemoryRecordKind.USER_ASSERTION else "agent"
                    turn = (
                        Turn(req.sender_id, self._record_text(req.kind, req.record_id, req.sender_id, req.content))
                        .id(key)
                        .content_type(req.content_type)
                        .metadata("sender_role", role)
                        .metadata("memory_record_kind", req.kind.value)
                    )
                    await session.observe(turn)
                else:
                    source = (
                        IngestSource.from_text(self._record_text(req.kind, req.record_id, req.sender_id, req.content))
                        .with_id(key)
                        .with_mime("text/markdown")
                    )
                    await session.ingest(source)
            ctx.send(RecordMemoryResult(record_id=req.record_id, session_id=req.session_id, kind=req.kind))
        except Exception:
            logger.exception("Memory record failed")
            self._send_failure(ctx, "record_failed")

    @agent.processor(FinalizeMemorySessionRequest, depends_on=["uniko"])
    async def finalize_memory_session(self, ctx: ProcessContext[FinalizeMemorySessionRequest], uniko: uniko.Agent):
        try:
            async with self._session_lock(ctx.payload.session_id):
                report = await uniko.finalize_session(ctx.payload.session_id)
            ctx.send(
                FinalizeMemorySessionResult(
                    session_id=ctx.payload.session_id,
                    rebuilt=bool(getattr(report, "rebuilt", False)),
                    transcript_chunks=len(getattr(report, "transcript_chunks", []) or []),
                    observation_chunks=len(getattr(report, "observation_chunks", []) or []),
                )
            )
        except Exception:
            logger.exception("Memory session finalization failed")
            self._send_failure(ctx, "finalize_failed")

    @agent.processor(ForgetMemoryRecordRequest, depends_on=["uniko"])
    async def forget_memory_record(self, ctx: ProcessContext[ForgetMemoryRecordRequest], uniko: uniko.Agent):
        try:
            key = self._record_key(ctx.payload.kind, ctx.payload.record_id)
            session = uniko.session(ctx.payload.session_id)
            if ctx.payload.kind in {MemoryRecordKind.USER_ASSERTION, MemoryRecordKind.ASSISTANT_RESPONSE}:
                report = await session.forget_turn(key)
            else:
                report = await session.delete_document(key)
            ctx.send(self._deletion_result(report))
        except Exception:
            logger.exception("Memory record forget failed")
            self._send_failure(ctx, "forget_failed")

    @agent.processor(DeleteMemorySessionRequest, depends_on=["uniko"])
    async def delete_memory_session(self, ctx: ProcessContext[DeleteMemorySessionRequest], uniko: uniko.Agent):
        try:
            ctx.send(self._deletion_result(await uniko.delete_session(ctx.payload.session_id)))
        except Exception:
            logger.exception("Memory session deletion failed")
            self._send_failure(ctx, "forget_failed")

    @agent.processor(ForgetMemoryParticipantRequest, depends_on=["uniko"])
    async def forget_memory_participant(self, ctx: ProcessContext[ForgetMemoryParticipantRequest], uniko: uniko.Agent):
        try:
            ctx.send(self._deletion_result(await uniko.forget_participant(ctx.payload.participant_id)))
        except Exception:
            logger.exception("Memory participant forget failed")
            self._send_failure(ctx, "forget_failed")

    # ========== Observation Processors ==========

    @agent.processor(ObserveTurnRequest, depends_on=["uniko"])
    async def observe_turn(self, ctx: ProcessContext[ObserveTurnRequest], uniko: uniko.Agent):
        """Observe a conversation turn and extract knowledge.

        Maps incoming message to uniko Turn, observes it, and returns
        extraction results. Auto-creates sessions if needed.

        Args:
            ctx: Process context with ObserveTurnRequest payload
            uniko: Guild-scoped uniko agent (injected dependency)
        """
        req = ctx.payload

        logger.debug(
            f"Observing turn from sender: {req.sender_id}, content: {req.content}, session_id: {req.session_id}"
        )

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

        except Exception:
            logger.exception("Memory observation failed")
            self._send_failure(ctx, "observation_failed")

    # ========== Recall Processors ==========

    @agent.processor(RecallRequest, depends_on=["uniko"])
    async def recall_knowledge(self, ctx: ProcessContext[RecallRequest], uniko: uniko.Agent):
        """Recall knowledge from memory based on query.

        Performs 3-phase cascade recall and returns ranked items with sources.

        Args:
            ctx: Process context with RecallRequest payload
            uniko: Guild-scoped uniko agent (injected dependency)
        """
        req = ctx.payload

        logger.debug("Recalling bounded knowledge for an explicit memory scope")

        try:
            sessions = req.scope.sessions
            if sessions is None:
                sessions = list(getattr(self, "_session_locks", {}))
            locks = [self._session_lock(session_id) for session_id in sorted(set(sessions))]
            for lock in locks:
                await lock.acquire()
            try:
                bundle = await uniko.recall_in(req.query, self._build_scope(req.scope))
            finally:
                for lock in reversed(locks):
                    lock.release()
            allowed = set(req.allowed_record_kinds)
            items: list[RecallItem] = []
            used_characters = 0
            truncated = False

            for native_item in bundle.items:
                item = self._serialize_recall_item(native_item)
                if item is None or item.record_kind not in allowed:
                    continue
                if len(items) >= req.item_limit:
                    truncated = True
                    break
                remaining = req.max_characters - used_characters
                if remaining <= 0:
                    truncated = True
                    break
                if len(item.content) > remaining:
                    item = item.model_copy(update={"content": item.content[:remaining]})
                    truncated = True
                items.append(item)
                used_characters += len(item.content)

            logger.debug(f"Serialized {len(items)} recall items for response.")

            ctx.send(
                RecallResponse(
                    items=items,
                    total_tokens=sum((len(item.content) + 3) // 4 for item in items),
                    phase1_only=bundle.phase1_only if hasattr(bundle, "phase1_only") else False,
                    phase2_only=bundle.phase2_only if hasattr(bundle, "phase2_only") else False,
                    coverage=bundle.coverage if hasattr(bundle, "coverage") else 0.0,
                    truncated=truncated,
                )
            )

        except Exception:
            logger.exception("Memory recall failed")
            self._send_failure(ctx, "recall_failed")

    @agent.processor(AnswerRequest, depends_on=["uniko"])
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
            context_items = [
                serialized
                for item in answer.context.items
                if (serialized := self._serialize_recall_item(item)) is not None
            ]

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

        except Exception as exc:
            # Preserve the actionable category, but never expose provider or memory details.
            error_msg = str(exc)
            if (
                "LLM not configured" in error_msg
                or "config error" in error_msg.lower()
                and "requires an LLM" in error_msg
            ):
                self._send_failure(ctx, "llm_not_configured")
            else:
                logger.exception("Memory answer generation failed")
                self._send_failure(ctx, "answer_failed")

    # ========== Helper Methods ==========

    def _build_scope(self, spec: Any) -> Scope:
        """Build a Uniko scope from a typed or legacy scope model."""
        if hasattr(spec, "sessions"):
            sessions = spec.sessions
            participants = spec.participants
        else:
            sessions = spec.get("sessions", [])
            participants = spec.get("participants", [])
        scope = Scope()
        if sessions is not None:
            scope = scope.sessions(sessions)
        if participants:
            scope = scope.participants(participants)
        return scope

    def _serialize_recall_item(self, item: "uniko.RecallItem") -> Optional[RecallItem]:
        """Serialize native RecallItem to Pydantic model.

        Args:
            item: Native RecallItem

        Returns:
            Pydantic RecallItem model
        """
        sources = [self._serialize_source(source) for source in item.sources]
        source_ids = [
            identifier
            for source in sources
            for identifier in [source.get("message_id"), source.get("artifact_id"), source.get("chunk_id")]
            if identifier
        ]
        source_kind = next(
            (
                kind
                for source in sources
                for kind in [
                    self._record_kind(source.get("message_id")),
                    self._record_kind(source.get("artifact_id")),
                ]
                if kind is not None
            ),
            None,
        )
        envelope_kind, envelope_record_id, content = self._record_envelope(item.content)
        record_kind = source_kind or envelope_kind
        if record_kind is None:
            return None
        if envelope_record_id:
            source_ids.insert(0, envelope_record_id)

        return RecallItem(
            node_id=item.node_id,
            kind=item.kind,
            record_kind=record_kind,
            score=item.score,
            content=content,
            sources=sources,
            source_ids=list(dict.fromkeys(source_ids)),
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

    # ========== Document Ingestion Processors (Phase 2) ==========

    @agent.processor(
        IngestDocumentRequest,
        depends_on=["uniko", "filesystem:guild_fs:guild", "filesystem:agent_fs"],
    )
    async def ingest_document(
        self, ctx: ProcessContext[IngestDocumentRequest], uniko: uniko.Agent, agent_fs: FileSystem, guild_fs: FileSystem
    ):
        """Ingest a document into memory.

        Processes PDFs, HTML, markdown, and other document types.
        Supports files from guild filesystem via MediaLink (on_filesystem=True).

        Args:
            ctx: Process context with IngestDocumentRequest payload
            uniko: Agent-scoped Uniko handle; its resolver uses the agent filesystem.
            agent_fs: Private filesystem also injected by the Uniko resolver for persistence.
            guild_fs: Guild filesystem for reading files stored in guild storage
        """
        req = ctx.payload

        if not req.media_link.on_filesystem:
            self._send_failure(ctx, "document_rejected")
            return

        try:
            async with self._session_lock(req.session_id):
                session = uniko.session(req.session_id)
                # Interpret the reference only through the injected guild
                # filesystem. Its path contract and confinement are authoritative.
                file_path = req.media_link.url
                if getattr(guild_fs, "asynchronous", False):
                    content = await guild_fs._cat_file(file_path)
                else:
                    with guild_fs.open(file_path, "rb") as f:
                        content = f.read()

                source = (
                    IngestSource.from_bytes(content)
                    .with_mime(req.media_link.mimetype or "application/octet-stream")
                    .with_id(self._record_key(MemoryRecordKind.EXTERNAL_EVIDENCE, req.record_id))
                )

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
                    record_id=req.record_id,
                )
            )

        except Exception:
            logger.exception("Guild document ingestion failed")
            self._send_failure(ctx, "document_ingest_failed")

    @agent.processor(BatchSubmitRequest, depends_on=["uniko"])
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

        except Exception:
            logger.exception("Memory batch submission failed")
            self._send_failure(ctx, "batch_submit_failed")

    # ========== Goal Management Processors (Phase 2) ==========

    @agent.processor(CreateGoalRequest, depends_on=["uniko"])
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

        except Exception:
            logger.exception("Memory goal creation failed")
            self._send_failure(ctx, "create_goal_failed")

    @agent.processor(UpdateGoalRequest, depends_on=["uniko"])
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

        except Exception:
            logger.exception("Memory goal update failed")
            self._send_failure(ctx, "update_goal_failed")

    @agent.processor(GetGoalsRequest, depends_on=["uniko"])
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

        except Exception:
            logger.exception("Memory goal retrieval failed")
            self._send_failure(ctx, "get_goals_failed")

    # ========== Task Management Processors (Phase 2) ==========

    @agent.processor(CreateTaskRequest, depends_on=["uniko"])
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

        except Exception:
            logger.exception("Memory task creation failed")
            self._send_failure(ctx, "create_task_failed")

    @agent.processor(UpdateTaskRequest, depends_on=["uniko"])
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

        except Exception:
            logger.exception("Memory task update failed")
            self._send_failure(ctx, "update_task_failed")

    @agent.processor(GoalContextRequest, depends_on=["uniko"])
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
                [{"message_id": message_id} for message_id in context.recent_messages] if req.include_episodes else []
            )

            ctx.send(
                GoalContext(
                    goal=goal_view,
                    tasks=tasks,
                    episodes=episodes,
                    progress={"facts": context.facts, "entities": context.entities, "sessions": context.sessions},
                )
            )

        except Exception:
            logger.exception("Memory goal context retrieval failed")
            self._send_failure(ctx, "get_goal_context_failed")

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
