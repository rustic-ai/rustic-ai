"""Comprehensive memory agent leveraging uniko's cognitive memory system."""

import asyncio
from contextlib import asynccontextmanager, nullcontext
from copy import copy
from hashlib import sha256
import logging
import threading
import time
from types import SimpleNamespace
from typing import Any, Dict, Optional
from uuid import uuid4

import uniko
from uniko import IngestSource, RecallSource, Scope, Turn

from rustic_ai.core.guild import agent
from rustic_ai.core.guild.agent import Agent, ProcessContext
from rustic_ai.core.guild.agent_ext.depends.filesystem import FileSystem
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ArrayOfContentParts,
    ChatCompletionRequest,
    ChatCompletionResponse,
    TextContentPart,
    UserMessage,
)
from rustic_ai.core.messaging.core.message import Message, ProcessStatus

from .config import MemoryAgentConfig
from .integration import (
    OperationGate,
    apply_provenance,
    bound_items,
    build_source,
    count_tokens,
    ingest_outcome,
    mime_type,
    native_scope,
    serialize_source,
)
from .models import (
    AnswerRequest,
    AnswerResponse,
    BatchItemOutcome,
    BatchSubmitRequest,
    BatchSubmitResponse,
    DeleteMemorySessionRequest,
    FinalizeMemorySessionRequest,
    FinalizeMemorySessionResult,
    ForgetMemoryParticipantRequest,
    ForgetMemoryRecordRequest,
    IngestDocumentRequest,
    MemoryAgentError,
    MemoryDeletionResult,
    MemoryRecordKind,
    MemoryScope,
    MemorySource,
    MemoryViewer,
    ObserveResult,
    ObserveTurnRequest,
    RecallItem,
    RecallRequest,
    RecallResponse,
    RecallUserSessionsRequest,
    RecordMemoryRequest,
    RecordMemoryResult,
)
from .structured import StructuredMemoryTools
from .tools import MemoryTools

logger = logging.getLogger(__name__)

_GATE_INITIALIZATION_LOCK = threading.Lock()

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


class _BatchItemCancelled(asyncio.CancelledError):
    """Carry the current item's terminal outcome through batch cancellation."""

    def __init__(self, outcome: BatchItemOutcome):
        super().__init__()
        self.outcome = outcome


def _document_context_live(context: dict | None) -> bool:
    """Honor optional workflow deadlines while preserving ordinary direct calls."""
    context = context or {}
    if "document_deadline_ms" not in context:
        return True
    deadline = context["document_deadline_ms"]
    return isinstance(deadline, int) and not isinstance(deadline, bool) and time.time() * 1000 < deadline


def _document_dispatch_live(_agent: Agent, message: Message) -> bool:
    return _document_context_live(message.session_state)


class MemoryAgent(Agent[MemoryAgentConfig], MemoryTools, StructuredMemoryTools):
    """Private Uniko memory with shared input documents from the guild filesystem."""

    @asynccontextmanager
    async def _session_lock(self, session_id: str, handle=None):
        with _GATE_INITIALIZATION_LOCK:
            if not hasattr(self, "_operation_gate"):
                self._operation_gate = OperationGate()
        async with self._operation_gate.hold():
            from .runtime import MemoryHandle

            runtime = handle._runtime if isinstance(handle, MemoryHandle) else None
            # Accepted operations can finish their native subcalls after close
            # starts; new operations waiting on the gate are rejected.
            with runtime.operation() if runtime else nullcontext():
                yield

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

    def _conversation_identity(self, ctx: ProcessContext, producer_ids: list[str]) -> Optional[tuple[str, str]]:
        """Only explicitly routed messages with the initializer's request identity qualify."""
        context = ctx.get_context() or {}
        user = context.get("analysis_user") or context.get("request_user")
        session_id = context.get("analysis_session") or context.get("memory_session_id")
        request_id = context.get("analysis_request_id") or context.get("request_id")
        if (
            ctx.message.sender.id not in producer_ids
            or not isinstance(user, str)
            or not user.startswith("upa-")
            or not isinstance(session_id, str)
            or not session_id.startswith("analysis-")
            or not isinstance(request_id, str)
        ):
            return None
        digest = sha256(f"{self.guild_id}\0{user}\0{request_id}".encode()).hexdigest()
        if session_id != f"analysis-{digest}":
            return None
        user_digest = sha256(f"{self.guild_id}\0{user}".encode()).hexdigest()
        return session_id, f"user-{user_digest}"

    @agent.processor(ChatCompletionRequest, depends_on=["uniko"])
    async def record_conversation_request(self, ctx: ProcessContext[ChatCompletionRequest], uniko: uniko.Agent):
        identity = self._conversation_identity(ctx, self.config.conversation_request_producers)
        if identity is None:
            self._send_failure(ctx, "record_rejected")
            return
        session_id, user_id = identity
        users = [message for message in ctx.payload.messages if isinstance(message, UserMessage)]
        if not users:
            self._send_failure(ctx, "record_rejected")
            return
        content = users[-1].content
        if isinstance(content, ArrayOfContentParts):
            visible = "\n".join(part.text for part in content.root if isinstance(part, TextContentPart))
        else:
            visible = content
        text = visible.strip()[:16000] or "[User supplied a file attachment]"
        context = ctx.get_context() or {}
        key = self._record_key(
            MemoryRecordKind.CONVERSATION_TURN, context.get("request_id") or context["analysis_request_id"]
        )
        turn = (
            Turn(user_id, self._record_text(MemoryRecordKind.CONVERSATION_TURN, key, user_id, text))
            .id(key)
            .metadata("sender_role", "user")
            .metadata("memory_record_kind", MemoryRecordKind.CONVERSATION_TURN.value)
            .category(MemoryRecordKind.CONVERSATION_TURN.value)
        )
        try:
            async with self._session_lock(session_id, uniko):
                await uniko.session(session_id).observe(turn)
        except Exception:
            logger.exception("Conversation request recording failed")
            self._send_failure(ctx, "record_failed")

    @agent.processor(ChatCompletionResponse, depends_on=["uniko"])
    async def close_conversation_session(self, ctx: ProcessContext[ChatCompletionResponse], uniko: uniko.Agent):
        identity = self._conversation_identity(ctx, self.config.conversation_response_producers)
        if identity is None or ctx.message.process_status not in {ProcessStatus.COMPLETED, ProcessStatus.ERROR}:
            self._send_failure(ctx, "record_rejected")
            return
        if len(ctx.payload.choices) != 1 or not ctx.payload.choices[0].message.content:
            self._send_failure(ctx, "record_rejected")
            return
        session_id, _ = identity
        content = ctx.payload.choices[0].message.content.strip()[:16000]
        key = self._record_key(MemoryRecordKind.ASSISTANT_RESPONSE, str(ctx.message.id))
        turn = (
            Turn(
                ctx.message.sender.id,
                self._record_text(MemoryRecordKind.ASSISTANT_RESPONSE, key, ctx.message.sender.id, content),
            )
            .id(key)
            .metadata("sender_role", "agent")
            .metadata("memory_record_kind", MemoryRecordKind.ASSISTANT_RESPONSE.value)
            .category(MemoryRecordKind.ASSISTANT_RESPONSE.value)
        )
        try:
            async with self._session_lock(session_id, uniko):
                await uniko.session(session_id).observe(turn)
                await uniko.finalize_session(session_id)
        except Exception:
            logger.exception("Conversation session closure failed")
            self._send_failure(ctx, "finalize_failed")

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
        if req.kind == MemoryRecordKind.UNKNOWN or not self._producer_is_allowed(ctx, req.kind):
            self._send_failure(ctx, "record_rejected")
            return

        key = self._record_key(req.kind, req.record_id)
        try:
            async with self._session_lock(req.session_id, uniko):
                session = uniko.session(req.session_id)
                if req.kind in {MemoryRecordKind.USER_ASSERTION, MemoryRecordKind.ASSISTANT_RESPONSE}:
                    role = "user" if req.kind == MemoryRecordKind.USER_ASSERTION else "agent"
                    turn = (
                        Turn(req.sender_id, req.content)
                        .id(key)
                        .content_type(mime_type(req.content_type))
                        .metadata("sender_role", role)
                        .metadata("memory_record_kind", req.kind.value)
                    )
                    await session.observe(apply_provenance(turn, req, req.kind))
                else:
                    source = IngestSource.from_text(req.content).with_id(key).with_mime(mime_type(req.content_type))
                    await session.ingest(apply_provenance(source, req, req.kind))
            ctx.send(RecordMemoryResult(record_id=req.record_id, session_id=req.session_id, kind=req.kind))
        except Exception:
            logger.exception("Memory record failed")
            self._send_failure(ctx, "record_failed")

    @agent.processor(FinalizeMemorySessionRequest, depends_on=["uniko"])
    async def finalize_memory_session(self, ctx: ProcessContext[FinalizeMemorySessionRequest], uniko: uniko.Agent):
        try:
            async with self._session_lock(ctx.payload.session_id, uniko):
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
            async with self._session_lock(ctx.payload.session_id, uniko):
                session = uniko.session(ctx.payload.session_id)
                # A conversation_turn can be a legacy artifact or an observed turn.
                message = await uniko.data.message(key)
                if message is not None:
                    if message.session_id != ctx.payload.session_id:
                        raise ValueError("Record is outside the requested session")
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
            async with self._session_lock(ctx.payload.session_id, uniko):
                report = await uniko.delete_session(ctx.payload.session_id)
            ctx.send(self._deletion_result(report))
        except Exception:
            logger.exception("Memory session deletion failed")
            self._send_failure(ctx, "forget_failed")

    @agent.processor(ForgetMemoryParticipantRequest, depends_on=["uniko"])
    async def forget_memory_participant(self, ctx: ProcessContext[ForgetMemoryParticipantRequest], uniko: uniko.Agent):
        try:
            async with self._session_lock("*", uniko):
                report = await uniko.forget_participant(ctx.payload.participant_id)
            ctx.send(self._deletion_result(report))
        except Exception:
            logger.exception("Memory participant forget failed")
            self._send_failure(ctx, "forget_failed")

    # ========== Observation Processors ==========

    async def _turn(self, req: ObserveTurnRequest, guild_fs: Any = None, byte_counts=None) -> Turn:
        if len(req.attachments or []) > self.config.max_attachments:
            raise ValueError("Attachment count exceeds limit")
        # Translate every source before any native write, including bounded FS reads.
        sources = []
        for spec in req.attachments or []:
            available = self.config.max_source_bytes
            if byte_counts is not None:
                available = min(available, self.config.max_unit_bytes - sum(byte_counts))
                if available < 0:
                    raise ValueError("Atomic unit exceeds byte limit")
            sources.append(await build_source(spec, guild_fs, available, byte_counts))
        turn = (
            Turn(req.sender_id, req.content)
            .id(req.message_id or str(uuid4()))
            .content_type(mime_type(req.content_type))
        )
        if req.timestamp:
            turn = turn.at(req.timestamp)
        if req.addressed_to:
            turn = turn.addressed_to(req.addressed_to)
        for key, value in (req.metadata or {}).items():
            turn = turn.metadata(key, value)
        turn = apply_provenance(turn, req, MemoryRecordKind.CONVERSATION_TURN)
        for source in sources:
            turn = turn.attach(source)
        for call in req.tool_calls:
            turn = turn.tool_call(self._tool(call))
        return turn

    @agent.processor(ObserveTurnRequest, depends_on=["uniko", "filesystem:guild_fs:guild"])
    async def observe_turn(
        self, ctx: ProcessContext[ObserveTurnRequest], uniko: uniko.Agent, guild_fs: FileSystem = None
    ):
        req = ctx.payload
        if req.tool_calls:
            from .structured_models import CommitMemoryUnitRequest

            session_id = req.session_id or self.config.default_session_id or ctx.agent.guild_id
            command = CommitMemoryUnitRequest(session_id=session_id, turns=[req], operation_id=str(ctx.message.id))
            await self._command(ctx, uniko, "commit_memory_unit", guild_fs, request=command, observe_response=True)
            return
        if not self._producer_is_allowed(ctx, MemoryRecordKind.CONVERSATION_TURN):
            self._send_failure(ctx, "record_rejected")
            return
        session_id = req.session_id or self.config.default_session_id or ctx.agent.guild_id
        try:
            turn = await self._turn(req, guild_fs)
            async with self._session_lock(session_id, uniko):
                result = await uniko.session(session_id).observe(turn)
                # observe() is synchronous with extraction in direct mode; flush is
                # exclusively a streaming operation and not required for observe().
            ctx.send(
                ObserveResult(
                    message_node_id=result.message_node_id,
                    chunk_node_ids=result.chunk_node_ids,
                    session_node_id=result.session_node_id,
                    sender_node_id=result.sender_node_id,
                    sender_id=result.sender_id,
                    extracted_entities=result.extracted_entities,
                    extracted_observations=result.extracted_observations,
                    attachment_count=len(result.attachments),
                    attachments=[ingest_outcome(x) for x in result.attachments],
                )
            )
        except Exception:
            logger.exception("Memory observation failed")
            self._send_failure(ctx, "observation_failed")

    # ========== Recall Processors ==========

    @agent.processor(RecallRequest, depends_on=["uniko"], predicate=_document_dispatch_live)
    async def recall_knowledge(self, ctx: ProcessContext[RecallRequest], uniko: uniko.Agent):
        """Recall knowledge from memory based on query.

        Performs 3-phase cascade recall and returns ranked items with sources.

        Args:
            ctx: Process context with RecallRequest payload
            uniko: Guild-scoped uniko agent (injected dependency)
        """
        if not _document_context_live(ctx.get_context()):
            return
        try:
            await self._recall(ctx, uniko, ctx.payload, ctx.payload.scope.sessions)
        except Exception:
            logger.exception("Memory recall failed")
            self._send_failure(ctx, "recall_failed")

    @agent.processor(RecallUserSessionsRequest, depends_on=["uniko"])
    async def recall_user_sessions(self, ctx: ProcessContext[RecallUserSessionsRequest], uniko: uniko.Agent):
        identity = self._conversation_identity(ctx, self.config.conversation_request_producers)
        if identity is None or identity[0] != ctx.payload.current_session_id:
            self._send_failure(ctx, "record_rejected")
            return
        try:
            # The participant is derived from the authenticated User Proxy identity,
            # never from a user-supplied Cypher fragment or a shared agent-wide scope.
            context = ctx.get_context() or {}
            if ctx.payload.user_id != (context.get("analysis_user") or context.get("request_user")):
                self._send_failure(ctx, "record_rejected")
                return
            rows = await uniko.query(
                "MATCH (p:Participant {participant_id: '" + identity[1] + "'})"
                "-[:PARTICIPATED_IN]->(s:Session) "
                "WHERE s.ended_at IS NOT NULL "
                "RETURN s.session_id AS sid ORDER BY s.ended_at DESC LIMIT 33"
            )
            sessions = list(
                dict.fromkeys(
                    row["sid"]
                    for row in rows
                    if isinstance(row.get("sid"), str) and row["sid"] != ctx.payload.current_session_id
                )
            )[:32]
            if not sessions:
                ctx.send(RecallResponse(items=[], total_tokens=0, phase1_only=False, phase2_only=False, coverage=0.0))
                return
            await self._recall(ctx, uniko, ctx.payload, sessions)
        except Exception:
            logger.exception("User session recall failed")
            self._send_failure(ctx, "recall_failed")

    def _authorized_scope(self, ctx: ProcessContext, spec: MemoryScope) -> MemoryScope:
        # Viewer membership is deployment/routing supplied, never accepted from
        # the request. Private store isolation remains the default boundary.
        context = ctx.get_context() or {}
        if self.config.scope_producers and ctx.message.sender.id not in self.config.scope_producers:
            raise ValueError("Scope producer rejected")
        trusted = context.get("memory_viewer")
        if spec.viewer is not None:
            if ctx.message.sender.id not in self.config.viewer_producers or trusted != spec.viewer.model_dump():
                raise ValueError("Untrusted viewer membership")
        elif trusted is not None and ctx.message.sender.id in self.config.viewer_producers:
            spec = spec.model_copy(update={"viewer": MemoryViewer.model_validate(trusted)})
        return spec

    async def _recall(self, ctx: ProcessContext, uniko: uniko.Agent, req: Any, sessions: Optional[list[str]]):
        spec = req.scope if isinstance(req, RecallRequest) else MemoryScope(sessions=sessions)
        spec = self._authorized_scope(ctx, spec)
        token_budget = req.token_budget
        if token_budget is None and "recall_max_tokens" in self.config.model_fields_set:
            token_budget = self.config.recall_max_tokens
        if token_budget is None:
            from .resolver import runtime_info

            runtime = runtime_info(uniko)
            if runtime is not None:
                token_budget = runtime["instance"].config()["recall_token_budget"]
        options = dict(
            limit=req.item_limit,
            token_budget=token_budget,
            min_score=req.min_score,
            reranker=req.reranker,
            reference_ts=req.reference_ts,
        )
        options = {key: value for key, value in options.items() if value is not None}
        allowed = set(req.allowed_record_kinds)
        # Native categories prefilter new records. A separate bounded legacy pass
        # cannot backfill source/revision metadata; advertise those limitations.
        primary = spec.model_copy(
            update={
                "categories": spec.categories or [kind.value for kind in allowed if kind != MemoryRecordKind.UNKNOWN]
            }
        )
        async with self._session_lock("*", uniko):
            bundle = await uniko.recall_with(req.query, native_scope(primary), **options)
            legacy = await uniko.recall_with(
                req.query, native_scope(spec), **{**options, "limit": self.config.legacy_recall_limit}
            )
        merged: dict[int, RecallItem] = {}
        for candidate in [*bundle.items, *legacy.items]:
            item = self._serialize_recall_item(candidate)
            if item.record_kind in allowed and (not spec.categories or item.category in spec.categories):
                # Source/revision filters are native-only: null metadata must not
                # bypass a source restriction in the compatibility pass.
                if spec.sources and item.source_id not in spec.sources:
                    continue
                merged.setdefault(item.node_id, item)
        ranked = sorted(merged.values(), key=lambda item: item.score, reverse=True)
        items, truncated = bound_items(ranked, req.item_limit, req.max_characters, token_budget)
        ctx.send(
            RecallResponse(
                items=items,
                total_tokens=sum(item.token_count for item in items),
                phase1_only=getattr(bundle, "phase1_only", False),
                phase2_only=getattr(bundle, "phase2_only", False),
                coverage=getattr(bundle, "coverage", 0.0),
                truncated=truncated,
                legacy_compatibility=True,
                legacy_limitations=[
                    "Legacy metadata cannot be reconstructed; compatibility recall is bounded",
                    "Legacy records cannot satisfy native category, source or revision filters",
                ],
            )
        )

    @agent.processor(AnswerRequest, depends_on=["uniko"])
    async def answer_question(self, ctx: ProcessContext[AnswerRequest], uniko: uniko.Agent):
        """Answer a question using recalled context + LLM.

        Requires LLM configured in UnikoResolver.

        Args:
            ctx: Process context with AnswerRequest payload
            uniko: Guild-scoped uniko agent (injected dependency)
        """
        req = ctx.payload

        if req.max_tokens is not None:
            ctx.send_error(
                MemoryAgentError(
                    error="unsupported_control", message="Configure generation limits on the Guild synthesis LLM agent"
                )
            )
            return
        try:
            # Native answer keeps its entire authorized generation context.
            if req.scope:
                scope = native_scope(
                    self._authorized_scope(ctx, MemoryScope.model_validate({"sessions": None, **req.scope}))
                )
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
        return native_scope(
            spec if isinstance(spec, MemoryScope) else MemoryScope.model_validate({"sessions": None, **spec})
        )

    def _serialize_recall_item(self, item: "uniko.RecallItem") -> RecallItem:
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
        category = getattr(item, "category", None)
        try:
            category_kind = MemoryRecordKind(category) if category else None
        except ValueError:
            category_kind = None
        record_kind = category_kind or source_kind or envelope_kind or MemoryRecordKind.UNKNOWN
        if category is not None and envelope_record_id not in source_ids:
            # Native writes are authoritative. User-authored text that resembles
            # the old envelope is content, not another record's provenance.
            content = item.content
            envelope_record_id = None
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
            category=category,
            source_id=getattr(item, "source_id", None),
            revision_id=getattr(item, "revision_id", None),
            token_count=(getattr(item, "token_count", None) if content == item.content else None)
            or count_tokens(content),
            token_count_method="native" if content == item.content and hasattr(item, "token_count") else "cl100k_base",
            context=getattr(item, "context", None),
            address=getattr(item, "address", None),
            legacy_metadata=category is None,
        )

    def _serialize_source(self, source: RecallSource) -> Dict[str, Any]:
        """Serialize native RecallSource to dict.

        Args:
            source: Native RecallSource

        Returns:
            Dict with source information
        """
        return serialize_source(source)

    # ========== Document Ingestion Processors (Phase 2) ==========

    @agent.processor(
        IngestDocumentRequest,
        depends_on=["uniko", "filesystem:guild_fs:guild", "filesystem:agent_fs"],
        predicate=_document_dispatch_live,
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
        if not _document_context_live(ctx.get_context()):
            return
        req = ctx.payload

        if req.media_link is not None and not req.media_link.on_filesystem:
            self._send_failure(ctx, "document_rejected")
            return
        if not self._producer_is_allowed(ctx, MemoryRecordKind.EXTERNAL_EVIDENCE):
            self._send_failure(ctx, "document_rejected")
            return
        try:
            spec = req.source or MemorySource(media_link=req.media_link)
            updates = {
                key: value
                for key, value in req.model_dump(include={"category", "source_id", "revision_id"}).items()
                if value is not None
            }
            spec = spec.model_copy(
                update={**updates, "id": self._record_key(MemoryRecordKind.EXTERNAL_EVIDENCE, req.record_id)}
            )
            source = await build_source(spec, guild_fs, self.config.max_source_bytes)
            async with self._session_lock(req.session_id, uniko):
                outcome = await uniko.session(req.session_id).ingest(source)
                response = ingest_outcome(outcome, req.record_id)
                if response.was_deduplicated and response.stored and response.success:
                    # Deduplication reports newly created chunks, not artifact readiness.
                    # Query the immutable artifact under the same session mutation lock.
                    node_id = response.artifact_node_id
                    if not isinstance(node_id, int) or isinstance(node_id, bool) or node_id < 0:
                        raise ValueError("Invalid native artifact identity")
                    rows = await uniko.query(
                        "MATCH (a:Artifact)-[:HAS_CHUNK]->(c:Chunk) "
                        f"WHERE id(a) = {node_id} RETURN id(c) AS node_id LIMIT 1"
                    )
                    response.searchable = bool(rows)
            ctx.send(response)
        except Exception:
            logger.exception("Guild document ingestion failed")
            self._send_failure(ctx, "document_ingest_failed")

    @staticmethod
    def _batch_message_id(ctx, req, spec, index):
        return spec.get("message_id") or f"batch-{req.batch_id or ctx.message.id}:{index}"

    @staticmethod
    def _batch_command_failure(index, message_id, error):
        uncertain = error.error == "operation_outcome_unknown"
        details = error.details or {}
        return BatchItemOutcome(
            index=index,
            message_id=message_id,
            success=False,
            stored=None if uncertain else False,
            error=error.error,
            operation=details.get("operation"),
            operation_id=details.get("operation_id"),
        )

    async def _batch_item(self, ctx, session, spec, index, session_id, req, guild_fs, handle) -> BatchItemOutcome:
        try:
            turn_req = ObserveTurnRequest.model_validate(spec)
            if not self._producer_is_allowed(ctx, MemoryRecordKind.CONVERSATION_TURN):
                raise ValueError("Producer rejected")
            if turn_req.session_id is not None and turn_req.session_id != session_id:
                raise ValueError("Batch item session differs from batch scope")
            if turn_req.message_id is None:
                turn_req = turn_req.model_copy(update={"message_id": self._batch_message_id(ctx, req, spec, index)})
            if turn_req.tool_calls:
                from .structured_models import CommitMemoryUnitRequest

                sent: list[Any] = []
                errors: list[MemoryAgentError] = []
                item_ctx = SimpleNamespace(
                    payload=turn_req,
                    message=copy(ctx.message),
                    get_context=ctx.get_context,
                    send=sent.append,
                    send_error=errors.append,
                )
                command = CommitMemoryUnitRequest(
                    session_id=session_id,
                    turns=[turn_req],
                    unit_id=turn_req.message_id,
                )
                try:
                    await self._command(item_ctx, handle, "commit_memory_unit", guild_fs, request=command)
                except asyncio.CancelledError:
                    outcome = (
                        self._batch_command_failure(index, turn_req.message_id, errors[0])
                        if errors and errors[0].error == "operation_outcome_unknown"
                        else BatchItemOutcome(
                            index=index, message_id=turn_req.message_id, success=False, error="cancelled"
                        )
                    )
                    raise _BatchItemCancelled(outcome) from None
                if errors:
                    return self._batch_command_failure(index, turn_req.message_id, errors[0])
                observed = sent[0].turns[0]
                attachments = observed.attachments
                calls = observed.tool_calls
            else:
                turn = await self._turn(turn_req, guild_fs)
                async with self._session_lock(session_id, handle):
                    result = await session.observe(turn)
                attachments = [ingest_outcome(item) for item in getattr(result, "attachments", [])]
                calls = []
            success = not any(item.extraction_failed for item in attachments)
            return BatchItemOutcome(
                index=index,
                message_id=turn_req.message_id,
                success=success,
                stored=True,
                tool_calls=calls,
                attachments=attachments,
                error=None if success else "attachment_extraction_failed",
            )
        except Exception:
            logger.exception("Memory batch item failed")
            return BatchItemOutcome(
                index=index, message_id=spec.get("message_id"), success=False, error="item_rejected"
            )

    @agent.processor(BatchSubmitRequest, depends_on=["uniko", "filesystem:guild_fs:guild"])
    async def batch_submit(
        self, ctx: ProcessContext[BatchSubmitRequest], uniko: uniko.Agent, guild_fs: FileSystem = None
    ):
        req = ctx.payload
        session_id = req.session_id or self.config.default_session_id or ctx.agent.guild_id
        if len(req.turns) > self.config.max_batch_items:
            self._send_failure(ctx, "batch_submit_failed")
            return
        outcomes = []
        # Streaming submit/flush is retained for this API. Fail before writes if
        # the resolver advertises direct mode; accepted items survive failures.
        from .resolver import runtime_info

        runtime = runtime_info(uniko)
        if runtime is not None and not runtime["streaming"]:
            ctx.send_error(
                MemoryAgentError(
                    error="unsupported_control", message="Batch submit requires a streaming Uniko resolver"
                )
            )
            return
        try:
            session = uniko.session(session_id)
            for index, spec in enumerate(req.turns):
                outcomes.append(await self._batch_item(ctx, session, spec, index, session_id, req, guild_fs, uniko))
            flushed = False
            flush_error = None
            if req.flush_after:
                try:
                    async with self._session_lock(session_id, uniko):
                        await session.flush()
                    flushed = True
                except Exception:
                    logger.exception("Memory batch flush failed")
                    flush_error = "flush_failed"
            response = BatchSubmitResponse(
                submitted_count=sum(x.stored is True for x in outcomes),
                uncertain_count=sum(x.stored is None for x in outcomes),
                flushed=flushed,
                session_id=session_id,
                outcomes=outcomes,
                error=flush_error or ("operation_outcome_unknown" if any(x.stored is None for x in outcomes) else None),
            )
            for outcome in outcomes:
                ctx.send(outcome)
            ctx.send(response)
        except asyncio.CancelledError as exc:
            if isinstance(exc, _BatchItemCancelled):
                outcomes.append(exc.outcome)
            for index in range(len(outcomes), len(req.turns)):
                outcome = BatchItemOutcome(
                    index=index,
                    message_id=self._batch_message_id(ctx, req, req.turns[index], index),
                    success=False,
                    error="cancelled",
                )
                outcomes.append(outcome)
            for outcome in outcomes:
                ctx.send(outcome)
            ctx.send(
                BatchSubmitResponse(
                    submitted_count=sum(x.stored is True for x in outcomes),
                    uncertain_count=sum(x.stored is None for x in outcomes),
                    flushed=False,
                    session_id=session_id,
                    outcomes=outcomes,
                    error="operation_outcome_unknown" if any(x.stored is None for x in outcomes) else "cancelled",
                )
            )
            raise
        except Exception:
            logger.exception("Memory batch failed")
            for outcome in outcomes:
                ctx.send(outcome)
            ctx.send(
                BatchSubmitResponse(
                    submitted_count=sum(x.stored is True for x in outcomes),
                    uncertain_count=sum(x.stored is None for x in outcomes),
                    flushed=False,
                    session_id=session_id,
                    outcomes=outcomes,
                    error="batch_failed",
                )
            )
