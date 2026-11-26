"""Deterministic ingestion barriers and bounded recall over typed messages."""

from collections import OrderedDict
from dataclasses import dataclass, field
from hashlib import sha256
import json
import threading
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from rustic_ai.core.guild.agent import Agent, ProcessContext, ProcessorHelper, processor
from rustic_ai.core.guild.agent_ext.mixins.scheduler import SchedulerMixin
from rustic_ai.core.messaging.core.message import JsonDict, Message
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name

from .document_models import (
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
    stage: str = "normalizing"
    pending: dict[str, list[int]] = field(default_factory=dict)


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
        self._workflow_lock = threading.RLock()
        self._workflows: dict[str, _Workflow] = {}
        self._completed: OrderedDict[str, None] = OrderedDict()
        self._closing = False

    def on_shutdown(self) -> None:
        with self._workflow_lock:
            self._closing = True
            self._workflows.clear()
        self.shutdown_scheduler()

    def _remember_completed(self, request_id: str) -> None:
        self._completed[request_id] = None
        while len(self._completed) > self.config.completed_request_limit:
            self._completed.popitem(last=False)

    def _terminal(self, state: _Workflow, error: str | None = None, recall: RecallResponse | None = None) -> _Outbound:
        self._workflows.pop(state.request_id, None)
        self._remember_completed(state.request_id)
        self.cancel_timer(state.attempt_id)
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
                if action.stage != "terminal" and self._workflows.get(state.request_id) is not state:
                    continue
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
        try:
            request = ctx.payload
        except ValidationError:
            raw_id = ctx.message.payload.get("request_id")
            ctx.send_error(
                DocumentWorkflowError(
                    request_id=raw_id[:256] if isinstance(raw_id, str) else "invalid-request",
                    error="document_request_invalid",
                    message="Document request is invalid.",
                )
            )
            return
        fingerprint = sha256(
            json.dumps(request.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        with self._workflow_lock:
            if self._closing or request.request_id in self._completed:
                return
            existing = self._workflows.get(request.request_id)
            if existing:
                actions = (
                    [] if existing.fingerprint == fingerprint else [self._terminal(existing, "request_id_conflict")]
                )
                state = None
            else:
                # Keep the original envelope/forwarding metadata, without retaining
                # another large copy of the incoming document bodies.
                origin = ctx.message.model_copy(update={"payload": request.model_dump(exclude={"sources"})})
                state = _Workflow(
                    request.request_id,
                    uuid4().hex,
                    fingerprint,
                    origin,
                    request.query,
                    request.allow_partial,
                    request.require_evidence,
                    [DocumentSourceOutcome(index=index) for index in range(len(request.sources))],
                )
                actions = []
                if len(self._workflows) >= self.config.max_active_workflows:
                    actions = [self._terminal(state, "document_capacity_exceeded")]
                    state = None
                else:
                    self._workflows[state.request_id] = state
                    self.schedule_once(
                        key=state.attempt_id,
                        delay_seconds=self.config.deadline_seconds,
                        payload=DocumentWorkflowDeadline(
                            request_id=state.request_id, attempt_id=state.attempt_id
                        ).model_dump(),
                        format=get_qualified_class_name(DocumentWorkflowDeadline),
                    )
        self._publish(actions)
        if state is None:
            return
        prepared: dict[str, Any] = {}
        total_bytes = 0
        for index, source in enumerate(request.sources):
            with self._workflow_lock:
                if self._workflows.get(state.request_id) is not state:
                    return
            try:
                snapshot, outcome, size = await snapshot_document(
                    source, self.config.corpus_session_id, guild_fs, self.config.max_source_bytes, index
                )
                assert outcome.record_id is not None
                total_bytes += size
                if total_bytes > self.config.max_workflow_bytes:
                    raise ValueError("Workflow exceeds byte limit")
                with self._workflow_lock:
                    if self._workflows.get(state.request_id) is not state:
                        return
                    state.sources[index] = outcome
                    state.pending.setdefault(outcome.record_id, []).append(index)
                    prepared[outcome.record_id] = snapshot
            except Exception:
                with self._workflow_lock:
                    if self._workflows.get(state.request_id) is not state:
                        return
                    state.sources[index] = DocumentSourceOutcome(
                        index=index, status="failed", error="document_source_rejected"
                    )
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
        with self._workflow_lock:
            state = self._workflows.get(ctx.payload.request_id)
            if state is None or state.attempt_id != ctx.payload.attempt_id or self._closing:
                return
            for item in state.sources:
                if item.status == "pending":
                    item.status = "unknown"
                    item.error = "document_outcome_unknown"
            actions = [self._terminal(state, "document_workflow_timed_out")]
        self._publish(actions)
