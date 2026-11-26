"""Deterministic ingestion barriers and bounded recall over typed messages."""

import asyncio
from collections import OrderedDict
from dataclasses import dataclass, field
from hashlib import sha256
import json
import re
import threading
import time
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from rustic_ai.core.guild.agent import Agent, ProcessContext, ProcessorHelper, processor
from rustic_ai.core.guild.agent_ext.mixins.scheduler import SchedulerMixin
from rustic_ai.core.messaging.core.message import JsonDict, Message

from .document_context import compact_document_context
from .document_models import (
    IDENTIFIER,
    DocumentCoordinatorConfig,
    DocumentSourceOutcome,
    DocumentWorkflowDeadline,
    DocumentWorkflowError,
    DocumentWorkflowRequest,
    DocumentWorkflowResult,
)
from .document_sources import snapshot_document
from .integration import bound_items
from .models import (
    IngestDocumentRequest,
    IngestOutcome,
    MemoryAgentError,
    MemoryScope,
    RecallRequest,
    RecallResponse,
)


def _fingerprint(request: DocumentWorkflowRequest) -> str:
    """Hash caller semantics without materializing an encoded document body."""
    digest = sha256()

    def visit(value):
        if isinstance(value, str):
            digest.update(b"s" + str(len(value)).encode() + b":")
            for offset in range(0, len(value), 4096):
                digest.update(value[offset : offset + 4096].encode("utf-8", errors="surrogatepass"))
        elif isinstance(value, dict):
            digest.update(b"{")
            for key in sorted(value):
                visit(key)
                visit(value[key])
            digest.update(b"}")
        elif isinstance(value, list):
            digest.update(b"[")
            for item in value:
                visit(item)
            digest.update(b"]")
        else:
            digest.update(json.dumps(value).encode() + b";")

    value = request.model_dump(mode="json", exclude={"sources"})
    value["sources"] = [source.model_dump(mode="json", exclude={"media_link": {"id"}}) for source in request.sources]
    visit(value)
    return digest.hexdigest()


@dataclass
class _Workflow:
    request_id: str
    attempt_id: str
    fingerprint: str
    origin: Message
    query: str | None
    allow_partial: bool
    require_evidence: bool
    sources: list[DocumentSourceOutcome]
    expires_at: float
    timer: threading.Timer | None = None
    stage: str = "normalizing"
    pending: dict[str, list[int]] = field(default_factory=dict)
    rejected: set[int] = field(default_factory=set)


@dataclass
class _Outbound:
    workflow: _Workflow
    payload: Any
    stage: str
    item: str | None = None
    error: bool = False


class DocumentCoordinatorAgent(Agent[DocumentCoordinatorConfig], SchedulerMixin):
    """Coordinate documents without owning access policy, synthesis or a store."""

    def __init__(self):
        self._init_scheduler()
        self._workflow_lock = threading.RLock()
        self._workflows: dict[str, _Workflow] = {}
        self._completed: OrderedDict[str, None] = OrderedDict()
        self._closing = False

    def on_shutdown(self) -> None:
        with self._workflow_lock:
            self._closing = True
            for state in self._workflows.values():
                if state.timer is not None:
                    state.timer.cancel()
            self._workflows.clear()
        self.shutdown_scheduler()

    def _remember_completed(self, request_id: str) -> None:
        self._completed[request_id] = None
        while len(self._completed) > self.config.completed_request_limit:
            self._completed.popitem(last=False)

    def _terminal(self, state: _Workflow, error: str | None = None, recall: RecallResponse | None = None) -> _Outbound:
        if self._workflows.get(state.request_id) is state and time.monotonic() >= state.expires_at:
            error = "document_workflow_timed_out"
        self._workflows.pop(state.request_id, None)
        self._remember_completed(state.request_id)
        if state.timer is not None:
            state.timer.cancel()
        state.stage = "terminal"
        payload: DocumentWorkflowError | DocumentWorkflowResult
        if error:
            for item in state.sources:
                if item.status == "pending":
                    item.status = "unknown"
                    item.error = "document_outcome_unknown"
            payload = DocumentWorkflowError(
                request_id=state.request_id,
                error=error,
                message=error.replace("_", " ").capitalize() + ".",
                sources=state.sources,
            )
        else:
            payload = DocumentWorkflowResult(
                request_id=state.request_id,
                query=state.query,
                sources=state.sources,
                recall=recall,
                partial=any(item.status in {"failed", "unknown"} for item in state.sources),
            )
        return _Outbound(state, payload, "terminal", error=bool(error))

    def _publish(self, outbound: list[_Outbound]) -> None:
        # Sync bus delivery can re-enter on another thread. Never publish under
        # the barrier lock; use a fresh context per branch to avoid context races.
        for action in outbound:
            state = action.workflow
            with self._workflow_lock:
                if self._closing:
                    return
                if action.stage != "terminal":
                    if self._workflows.get(state.request_id) is not state:
                        continue
                    if time.monotonic() >= state.expires_at:
                        action = self._terminal(state, "document_workflow_timed_out")
            ctx = self._make_process_context(
                state.origin,
                "coordinate",
                JsonDict,
                ProcessorHelper.get_on_send_fixtures(type(self)),
                ProcessorHelper.get_on_error_fixtures(type(self)),
                ProcessorHelper.get_message_mod_fixtures(type(self)),
            )
            ctx.update_context(
                {
                    "document_request_id": state.request_id,
                    "document_attempt_id": state.attempt_id,
                    "document_stage": action.stage,
                    "document_item": action.item,
                }
            )
            if action.error:
                ctx.send_error(action.payload)
            else:
                ctx.send(action.payload)

    def _advance(self, state: _Workflow) -> list[_Outbound]:
        if state.pending:
            return []
        failed = any(item.status == "failed" for item in state.sources)
        if failed and not state.allow_partial:
            return [self._terminal(state, "document_ingestion_failed")]
        if state.query is None:
            if state.sources and all(item.status == "failed" for item in state.sources):
                return [self._terminal(state, "document_ingestion_failed")]
            return [self._terminal(state)]
        state.stage = "recall"
        request = RecallRequest(
            query=state.query,
            scope=MemoryScope(sessions=[self.config.corpus_session_id]),
            allowed_record_kinds=["external_evidence"],
            item_limit=self.config.recall_item_limit,
            max_characters=self.config.recall_max_characters,
            token_budget=self.config.recall_token_budget,
        )
        return [_Outbound(state, request, "recall")]

    def _state_for_reply(self, ctx: ProcessContext, stage: str | None) -> _Workflow | None:
        if ctx.message.sender.id != self.config.memory_agent_id:
            return None
        context = ctx.get_context() or {}
        state = self._workflows.get(context.get("document_request_id", ""))
        if (
            state is None
            or self._closing
            or state.attempt_id != context.get("document_attempt_id")
            or state.stage != stage
            or context.get("document_stage") != stage
        ):
            return None
        return state

    @processor(DocumentWorkflowRequest, depends_on=["filesystem:guild_fs:guild"])
    async def coordinate(self, ctx: ProcessContext[DocumentWorkflowRequest], guild_fs):
        started = time.monotonic()
        try:
            request = ctx.payload
        except ValidationError:
            self._reject_invalid(ctx, ctx.message.payload.get("request_id"), started)
            return
        state = self._admit_request(ctx, request, started)
        if state is None:
            return
        prepared = await self._prepare_documents(state, request, guild_fs)
        if prepared is None:
            return
        with self._workflow_lock:
            if self._workflows.get(state.request_id) is not state:
                return
            state.stage = "ingest"
            actions = [
                _Outbound(
                    state,
                    IngestDocumentRequest(
                        record_id=record_id,
                        session_id=self.config.corpus_session_id,
                        source=snapshot,
                    ),
                    "ingest",
                    record_id,
                )
                for record_id, snapshot in prepared.items()
            ]
            if not actions:
                actions = self._advance(state)
        self._publish(actions)

    def _reject_invalid(self, ctx: ProcessContext, raw_id: Any, started: float) -> None:
        usable_id = isinstance(raw_id, str) and 0 < len(raw_id) <= 256 and re.fullmatch(IDENTIFIER, raw_id) is not None
        request_id = raw_id[:256] if isinstance(raw_id, str) and raw_id else "invalid-request"
        with self._workflow_lock:
            if self._closing or (usable_id and request_id in self._completed):
                return
            existing = self._workflows.get(request_id) if usable_id else None
            if existing is not None:
                actions = [self._terminal(existing, "request_id_conflict")]
            else:
                state = self._new_state(ctx, request_id, started)
                if usable_id:
                    actions = [self._terminal(state, "document_request_invalid")]
                else:
                    # An anonymous malformed request has no deduplication key.
                    # Its display label must never tombstone a valid caller ID.
                    actions = [
                        _Outbound(
                            state,
                            DocumentWorkflowError(
                                request_id=request_id,
                                error="document_request_invalid",
                                message="Document request is invalid.",
                            ),
                            "terminal",
                            error=True,
                        )
                    ]
        self._publish(actions)

    def _admit_request(self, ctx: ProcessContext, request: DocumentWorkflowRequest, started: float) -> _Workflow | None:
        state: _Workflow | None
        # Admission happens before hashing any document bodies.
        with self._workflow_lock:
            if self._closing or request.request_id in self._completed:
                return None
            existing = self._workflows.get(request.request_id)
            if existing is None and len(self._workflows) >= self.config.max_active_workflows:
                actions = [
                    self._terminal(self._new_state(ctx, request.request_id, started), "document_capacity_exceeded")
                ]
                admitted = False
            else:
                actions = []
                admitted = True
        self._publish(actions)
        if not admitted:
            return None
        # Cheap inline length guards precede canonical hashing and UTF-8/base64
        # expansion. Hashing remains incremental even for rejected sources.
        rejected = {
            index
            for index, source in enumerate(request.sources)
            if (source.text is not None and len(source.text) > self.config.max_source_bytes)
            or (
                source.base64_data is not None
                and len(source.base64_data) > 4 * ((self.config.max_source_bytes + 2) // 3)
            )
        }
        fingerprint = _fingerprint(request)
        with self._workflow_lock:
            if self._closing or request.request_id in self._completed:
                return None
            existing = self._workflows.get(request.request_id)
            if existing:
                actions = (
                    [] if existing.fingerprint == fingerprint else [self._terminal(existing, "request_id_conflict")]
                )
                state = None
            else:
                state = self._new_state(ctx, request.request_id, started, request, fingerprint)
                if len(self._workflows) >= self.config.max_active_workflows:
                    actions = [self._terminal(state, "document_capacity_exceeded")]
                    state = None
                else:
                    self._workflows[state.request_id] = state
                    state.timer = threading.Timer(
                        max(0, state.expires_at - time.monotonic()),
                        self._expire,
                        args=(state.request_id, state.attempt_id),
                    )
                    state.timer.daemon = True
                    state.timer.start()
                    actions = []
        self._publish(actions)
        if state is not None:
            state.rejected = rejected
        return state

    async def _prepare_documents(
        self, state: _Workflow, request: DocumentWorkflowRequest, guild_fs
    ) -> dict[str, Any] | None:
        prepared: dict[str, Any] = {}
        total_bytes = 0
        for index, source in enumerate(request.sources):
            with self._workflow_lock:
                if self._workflows.get(state.request_id) is not state:
                    return None
            try:
                remaining = state.expires_at - time.monotonic()
                if remaining <= 0:
                    self._expire(state.request_id, state.attempt_id)
                    return None
                if index in state.rejected:
                    raise ValueError("Source exceeds byte limit")
                snapshot, outcome, size = await asyncio.wait_for(
                    snapshot_document(
                        source,
                        self.config.corpus_session_id,
                        guild_fs,
                        min(self.config.max_source_bytes, self.config.max_workflow_bytes - total_bytes),
                        index,
                    ),
                    timeout=remaining,
                )
                assert outcome.record_id is not None
                total_bytes += size
                if total_bytes > self.config.max_workflow_bytes:
                    raise ValueError("Workflow exceeds byte limit")
                with self._workflow_lock:
                    if self._workflows.get(state.request_id) is not state:
                        return None
                    state.sources[index] = outcome
                    state.pending.setdefault(outcome.record_id, []).append(index)
                    prepared[outcome.record_id] = snapshot
            except TimeoutError:
                self._expire(state.request_id, state.attempt_id)
                return None
            except Exception:
                with self._workflow_lock:
                    if self._workflows.get(state.request_id) is not state:
                        return None
                    state.sources[index] = DocumentSourceOutcome(
                        index=index, status="failed", error="document_source_rejected"
                    )
        return prepared

    def _new_state(self, ctx, request_id, started, request=None, fingerprint="") -> _Workflow:
        payload = request.model_dump(exclude={"sources"}) if request is not None else {"request_id": request_id}
        origin = ctx.message.model_copy(
            update={"payload": payload, "session_state": compact_document_context(ctx.get_context())}
        )
        return _Workflow(
            request_id=request_id,
            attempt_id=uuid4().hex,
            fingerprint=fingerprint,
            origin=origin,
            query=request.query if request else None,
            allow_partial=request.allow_partial if request else False,
            require_evidence=request.require_evidence if request else True,
            sources=[DocumentSourceOutcome(index=index) for index in range(len(request.sources))] if request else [],
            expires_at=started + self.config.deadline_seconds,
        )

    def _expire(self, request_id: str, attempt_id: str) -> None:
        # Expiration is independent of the agent's serialized inbox. Source
        # reads can be slow or non-cooperative without withholding the outcome.
        with self._workflow_lock:
            state = self._workflows.get(request_id)
            if state is None or state.attempt_id != attempt_id or self._closing or time.monotonic() < state.expires_at:
                return
            actions = [self._terminal(state, "document_workflow_timed_out")]
        self._publish(actions)

    def _settle(self, state: _Workflow, record_id: str | None, outcome: IngestOutcome | None, error: str | None):
        if record_id is None:
            return []
        indices = state.pending.pop(record_id, [])
        for index in indices:
            item = state.sources[index]
            item.outcome = outcome
            item.error = error
            item.status = "failed" if error else "ingested"
        return self._advance(state) if indices else []

    @processor(IngestOutcome)
    def ingested(self, ctx: ProcessContext[IngestOutcome]):
        with self._workflow_lock:
            state = self._state_for_reply(ctx, "ingest")
            item = (ctx.get_context() or {}).get("document_item")
            if state is None or item != ctx.payload.record_id:
                return
            outcome = ctx.payload
            error = "document_ingestion_failed" if not outcome.success or not outcome.stored else None
            actions = self._settle(state, item, outcome, error)
        self._publish(actions)

    @processor(RecallResponse)
    def recalled(self, ctx: ProcessContext[RecallResponse]):
        with self._workflow_lock:
            state = self._state_for_reply(ctx, "recall")
            if state is None:
                return
            recall = ctx.payload
            items, truncated = bound_items(
                recall.items,
                self.config.recall_item_limit,
                self.config.recall_max_characters,
                self.config.recall_token_budget,
            )
            recall = recall.model_copy(
                update={
                    "items": items,
                    "truncated": recall.truncated or truncated,
                    "total_tokens": sum(item.token_count for item in items),
                }
            )
            error = "document_evidence_unavailable" if state.require_evidence and not items else None
            actions = [self._terminal(state, error, recall)]
        self._publish(actions)

    @processor(MemoryAgentError, handle_essential=True)
    def failed(self, ctx: ProcessContext[MemoryAgentError]):
        with self._workflow_lock:
            context = ctx.get_context() or {}
            stage = context.get("document_stage")
            state = self._state_for_reply(ctx, stage)
            if state is None:
                return
            if stage == "ingest":
                actions = self._settle(state, context.get("document_item"), None, ctx.payload.error)
            elif stage == "recall":
                actions = [self._terminal(state, "document_recall_failed")]
            else:
                return
        self._publish(actions)

    @processor(DocumentWorkflowDeadline, handle_essential=True)
    def deadline(self, ctx: ProcessContext[DocumentWorkflowDeadline]):
        if ctx.message.sender.id != self.id:
            return
        self._expire(ctx.payload.request_id, ctx.payload.attempt_id)
