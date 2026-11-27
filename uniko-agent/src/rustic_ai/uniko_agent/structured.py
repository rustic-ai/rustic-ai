"""Authorized native experience operations with durable at-most-once dispatch."""

import asyncio
import base64
from hashlib import sha256
import logging
from typing import AsyncContextManager

import uniko

from rustic_ai.core.guild import agent
from rustic_ai.core.guild.agent import ProcessContext
from rustic_ai.core.guild.agent_ext.depends.filesystem import FileSystem
from rustic_ai.core.messaging.core.message import ProcessStatus
from rustic_ai.core.utils.basic_class_utils import get_class_from_name

from .config import MemoryAgentConfig
from .integration import apply_provenance, ingest_outcome, native_scope
from .models import (
    CreateGoalRequest,
    CreateTaskRequest,
    GetGoalsRequest,
    GoalContext,
    GoalContextRequest,
    GoalsListResponse,
    GoalStatusResponse,
    GoalView,
    MemoryAgentError,
    MemoryRecordKind,
    MemoryScope,
    ObserveResult,
    TaskStatusResponse,
    TaskView,
    ToolCallOutcome,
    ToolCallSpec,
    UpdateGoalRequest,
    UpdateTaskRequest,
)
from .receipts import ReceiptConflict, canonical
from .resolver import runtime_info
from .structured_models import (
    ActionResponse,
    AddObservationRequest,
    AssertFactRequest,
    CommitMemoryUnitRequest,
    ConsolidateMemoryRequest,
    ConsolidationResponse,
    EpisodeResponse,
    ExperienceResponse,
    ExplainMemoryRuleRequest,
    FactInvalidationResponse,
    FactResponse,
    InvalidateFactRequest,
    ListMemoryRulesRequest,
    MatchProceduresRequest,
    MemoryOperationStatus,
    MemoryOperationStatusRequest,
    MemoryRulesResponse,
    MemoryRuleView,
    MemoryUnitResponse,
    ObservationResponse,
    ProcedureMatch,
    ProceduresResponse,
    ProcedureUseResponse,
    ReadExperienceRequest,
    RecordActionRequest,
    RecordEpisodeRequest,
    RecordProcedureUseRequest,
    RecordToolCallRequest,
    ToolCallResponse,
)
from .tools import literal, snapshot

# All labels/properties/edges are fixed, never supplied by the caller.
_RECORDS = {
    "goal": ("Goal", "goal_id", "OWNED_BY"),
    "task": ("Task", "task_id", "ASSIGNED_TO"),
    "action": ("Action", "action_id", "PERFORMED_BY"),
    "episode": ("Episode", "episode_id", "RECORDED_BY"),
    "observation": ("Observation", "observation_id", "ABOUT"),
    "fact": ("Fact", "fact_id", None),
    "procedure": ("Procedure", "procedure_id", None),
}
_RESPONSE_TYPES = {
    cls.__module__ + "." + cls.__name__
    for cls in (
        ActionResponse,
        EpisodeResponse,
        ObservationResponse,
        FactResponse,
        FactInvalidationResponse,
        ConsolidationResponse,
        MemoryUnitResponse,
        ProcedureUseResponse,
        ToolCallResponse,
        GoalView,
        TaskView,
        GoalStatusResponse,
        TaskStatusResponse,
        ObserveResult,
    )
}


class UnsupportedStructuredControl(ValueError):
    pass


class StructuredMemoryTools:
    config: MemoryAgentConfig

    def _session_lock(self, session_id: str, handle=None) -> AsyncContextManager:
        raise NotImplementedError

    def _producer_is_allowed(self, ctx: ProcessContext, kind: MemoryRecordKind) -> bool:
        raise NotImplementedError

    def _authorized_scope(self, ctx: ProcessContext, spec: MemoryScope) -> MemoryScope:
        raise NotImplementedError

    async def _source_allowed(self, handle, kind, identifier, spec) -> bool:
        raise NotImplementedError

    async def _turn(self, req, guild_fs=None, byte_counts=None):
        raise NotImplementedError

    @staticmethod
    def _structured_error(ctx, error):
        ctx.message.process_status = ProcessStatus.ERROR
        ctx.send_error(error)

    @staticmethod
    def _stable_id(actor: str, operation: str, key: str) -> str:
        return "rustic-" + operation + "-" + sha256(f"{actor}\0{operation}\0{key}".encode()).hexdigest()

    @staticmethod
    async def _actor(handle, actor: str, register: bool = False):
        info = runtime_info(handle)
        if info is None:
            raise ValueError("Structured operations require a managed Uniko resolver")
        runtime = info["runtime"]
        if register:
            if not runtime.organization_id:
                raise ValueError("A trusted organization is required for registration")
            # Register the reporting actor through the native identity API before
            # adding its trusted deployment organization membership.
            await runtime.instance.agent(actor).register()
            await runtime.instance.add_org_member(actor, runtime.organization_id)
        return runtime.wrap(runtime.instance.agent(actor))

    def _owner(self, ctx, requested=None):
        own = ctx.message.sender.id
        if requested is not None and requested != own and own not in self.config.scope_producers:
            raise ValueError("Owner selection is not authorized")
        return requested or own

    def _control(self, ctx):
        if ctx.message.sender.id not in self.config.control_producers:
            raise ValueError("Store-wide control producer rejected")

    async def _record(self, handle, kind, identifier):
        label, prop, edge = _RECORDS[kind]
        rows = await handle.query(
            f"MATCH (n:{label} {{{prop}: {literal(identifier)}}}) RETURN id(n) AS node_id LIMIT 1"
        )
        if not rows:
            return None
        row = dict(rows[0])
        if edge:
            owners = await handle.query(
                f"MATCH (n:{label} {{{prop}: {literal(identifier)}}})-[:{edge}]->(p:Participant) "
                "RETURN DISTINCT p.participant_id AS owner LIMIT 2"
            )
            row["owners"] = [r["owner"] for r in owners]
        return row

    async def _owned(self, handle, kind, identifier, owner, required=True):
        row = await self._record(handle, kind, identifier)
        if row is None:
            if required:
                raise ValueError("Referenced record does not exist")
            return None
        if "owners" in row and set(row["owners"]) != {owner}:
            raise ValueError("Record ownership is not authorized")
        return row

    async def _scoped(self, handle, kind, identifier, spec):
        label, prop, _ = _RECORDS[kind]
        active = any(
            (spec.sessions is not None, spec.participants, spec.categories, spec.sources, spec.since, spec.until)
        )
        query = f"MATCH (n:{label} {{{prop}: {literal(identifier)}}})"
        query += " WHERE id(n) IN $allow" if active else ""
        rows = await handle.query_in(query + " RETURN n.visibility AS visibility LIMIT 1", native_scope(spec))
        if not rows:
            raise ValueError("Referenced record is outside the authorized scope")
        visibility = rows[0].get("visibility")
        if visibility:
            viewer = spec.viewer
            permitted = (
                set()
                if viewer is None
                else {
                    f"private:{viewer.participant_id}",
                    *[f"team:{x}" for x in viewer.teams],
                    *[f"org:{x}" for x in viewer.orgs],
                }
            )
            if visibility not in permitted:
                raise ValueError("Record visibility is not authorized")

    def _visibility(self, spec, visibility):
        if visibility:
            viewer = spec.viewer
            permitted = (
                set()
                if viewer is None
                else {
                    f"private:{viewer.participant_id}",
                    *[f"team:{x}" for x in viewer.teams],
                    *[f"org:{x}" for x in viewer.orgs],
                }
            )
            if visibility not in permitted:
                raise ValueError("Requested visibility is not authorized")

    async def _preflight(self, ctx, handle, kind, req, actor, key, guild_fs):
        data = req.model_dump(exclude={"operation_id"})
        for name in ("started_at", "ended_at", "timestamp", "temporal_anchor", "observed_at", "deadline"):
            if name in data:
                data[name] = getattr(req, name)
        id_field = {
            "create_goal": "goal_id",
            "create_task": "task_id",
            "record_action": "action_id",
            "record_episode": "episode_id",
            "record_tool_call": "call_id",
            "commit_memory_unit": "unit_id",
        }.get(kind)
        if id_field:
            data[id_field] = data[id_field] or self._stable_id(actor, kind, key)
        if kind in ("consolidate_memory", "invalidate_fact", "record_procedure_use"):
            self._control(ctx)
        if kind == "create_goal":
            if req.parent_goal_id:
                await self._owned(handle, "goal", req.parent_goal_id, actor)
        if kind == "create_task":
            await self._owned(handle, "goal", req.goal_id, actor)
            for tid in (req.depends_on or []) + ([req.subtask_of_task_id] if req.subtask_of_task_id else []):
                await self._owned(handle, "task", tid, actor)
        if kind == "update_goal" and (req.metadata or (req.outcome is not None and req.action != "complete")):
            raise UnsupportedStructuredControl("Unsupported goal metadata or outcome control")
        if kind == "update_task" and req.outcome is not None:
            raise UnsupportedStructuredControl("Task outcomes require an explicit episode")
        for record_kind in ("goal", "task"):
            if kind == "update_" + record_kind:
                await self._owned(handle, record_kind, data[record_kind + "_id"], actor, required=False)
        if kind in ("create_goal", "create_task", "record_action", "record_episode", "record_tool_call"):
            rk = {
                "create_goal": "goal",
                "create_task": "task",
                "record_action": "action",
                "record_episode": "episode",
                "record_tool_call": "action",
            }[kind]
            identifier = data[id_field]
            existing = await self._owned(handle, rk, identifier, actor, required=False)
            if existing:
                raise ReceiptConflict("An existing native identity has no matching receipt")
        await self._preflight_links(ctx, handle, kind, req, data, actor)
        if kind == "commit_memory_unit":
            await self._prepare_unit(ctx, handle, req, data, actor, guild_fs)
        return data

    async def _preflight_links(self, ctx, handle, kind, req, data, actor):
        if kind in ("record_action", "record_episode", "record_tool_call"):
            if kind == "record_action" and req.session_id:
                rows = await handle.query(
                    f"MATCH (s:Session {{session_id: {literal(req.session_id)}}}) RETURN id(s) AS nid LIMIT 1"
                )
                if not rows:
                    raise ValueError("Referenced session does not exist")
            mid = data.get("triggered_by_message_id") or data.get("triggered_by")
            if mid and await handle.data.message(mid) is None:
                raise ValueError("Referenced message does not exist")
            for aid in data.get("involved_action_ids", []) + [
                x for x in (data.get("previous_action_id"), data.get("after")) if x
            ]:
                await self._owned(handle, "action", aid, actor)
        if kind in ("add_observation", "assert_fact", "invalidate_fact"):
            spec = self._authorized_scope(ctx, req.scope)
            self._visibility(spec, data.get("visibility"))
            if kind == "add_observation":
                if not await self._source_allowed(handle, "message", req.message_id, spec):
                    raise ValueError("Referenced message is outside the scope")
            for oid in data.get("supporting_observation_ids", []):
                await self._owned(handle, "observation", oid, actor)
                await self._scoped(handle, "observation", oid, spec)
            if kind == "invalidate_fact":
                for fid in [req.fact_id] + ([req.replacement_fact_id] if req.replacement_fact_id else []):
                    await self._scoped(handle, "fact", fid, spec)
        if kind == "record_procedure_use" and await self._record(handle, "procedure", req.procedure_id) is None:
            raise ValueError("Procedure does not exist")
        if kind == "record_tool_call":
            data["prepared"] = self._tool(req.model_copy(update={"call_id": data["call_id"]}))

    async def _prepare_unit(self, ctx, handle, req, data, actor, guild_fs):
        if not self._producer_is_allowed(ctx, MemoryRecordKind.CONVERSATION_TURN):
            raise ValueError("Conversation producer rejected")
        counts = []
        prepared = []
        message_ids = []
        known_messages = set()
        known_actions = set()
        for index, turn in enumerate(req.turns):
            if turn.tool_calls and turn.sender_id != actor:
                raise UnsupportedStructuredControl(
                    "Embedded tools require a reporting-agent turn; use separate user and reporter turns or standalone tool calls"
                )
            mid = turn.message_id or self._stable_id(actor, data["unit_id"], str(index))
            tools = []
            for j, call in enumerate(turn.tool_calls):
                if not self._producer_is_allowed(ctx, MemoryRecordKind.EXECUTED_RESULT):
                    raise ValueError("Tool producer rejected")
                cid = call.call_id or self._stable_id(actor, mid, str(j))
                if await self._record(handle, "action", cid) or cid in known_actions:
                    raise ReceiptConflict("Tool identity already exists outside this unit receipt")
                if call.triggered_by and call.triggered_by not in known_messages and call.triggered_by != mid:
                    if await handle.data.message(call.triggered_by) is None:
                        raise ValueError("Referenced message does not exist")
                if call.after and call.after not in known_actions:
                    await self._owned(handle, "action", call.after, actor)
                tools.append(call.model_copy(update={"call_id": cid}))
                known_actions.add(cid)
            if mid in known_messages or await handle.data.message(mid) is not None:
                raise ReceiptConflict("Turn identity already exists outside this unit receipt")
            turn = turn.model_copy(update={"message_id": mid, "tool_calls": tools})
            counts.append(len(canonical(turn.model_dump(mode="json")).encode()))
            if sum(counts) > self.config.max_unit_bytes:
                raise ValueError("Atomic unit exceeds byte limit")
            prepared.append(await self._turn(turn, guild_fs, counts))
            known_messages.add(mid)
            message_ids.append(mid)
        if sum(counts) > self.config.max_unit_bytes:
            raise ValueError("Atomic unit exceeds the prepared byte limit")
        data["prepared"] = prepared
        data["message_ids"] = message_ids

    def _tool(self, spec: ToolCallSpec):
        if len(canonical(spec.model_dump(mode="json")).encode()) > self.config.max_source_bytes:
            raise ValueError("Tool input/output exceeds byte limit")
        builder = uniko.ToolCall(spec.tool_name)
        for name in ("call_id", "arguments", "status", "error", "started_at", "ended_at", "triggered_by", "after"):
            value = getattr(spec, name)
            if value is not None or (name == "arguments" and name in spec.model_fields_set):
                builder = getattr(builder, name)(value)
        if spec.output_kind == "json":
            builder = builder.json_output(spec.json_output)
        elif spec.text_output is not None:
            builder = builder.text_output(spec.text_output)
        elif spec.base64_output is not None:
            builder = builder.bytes_output(
                base64.b64decode(spec.base64_output, validate=True), spec.mime_type or "application/octet-stream"
            )
        return apply_provenance(builder, spec, MemoryRecordKind.EXECUTED_RESULT)

    @staticmethod
    def _tool_outcome(value):
        return ToolCallOutcome(
            **snapshot(value, ("call_id", "action_node", "artifact_id", "artifact_node", "was_replay"))
        )

    def _observe_result(self, result, message_id=None):
        return ObserveResult(
            message_id=message_id,
            **snapshot(
                result,
                (
                    "message_node_id",
                    "chunk_node_ids",
                    "session_node_id",
                    "sender_node_id",
                    "sender_id",
                    "extracted_entities",
                    "extracted_observations",
                ),
            ),
            attachment_count=len(result.attachments),
            attachments=[ingest_outcome(x) for x in result.attachments],
            tool_calls=[self._tool_outcome(x) for x in result.tool_calls],
        )

    async def _goal_view(self, handle, goal):
        record = await self._record(handle, "goal", goal.goal_id)
        props = await handle.query(
            f"MATCH (g:Goal {{goal_id: {literal(goal.goal_id)}}}) RETURN g.guardrails AS guardrails"
        )
        parents = await handle.query(
            f"MATCH (g:Goal {{goal_id: {literal(goal.goal_id)}}})-[:PARENT_GOAL]->(p:Goal) RETURN p.goal_id AS parent"
        )
        return GoalView(
            **snapshot(
                goal,
                (
                    "goal_id",
                    "title",
                    "description",
                    "status",
                    "phase",
                    "completed_at",
                    "created_at",
                    "metrics",
                    "deadline",
                ),
            ),
            node_id=record["node_id"],
            guardrails=props[0].get("guardrails") if props else None,
            parent_goal_id=parents[0]["parent"] if parents else None,
            updated_at=goal.completed_at,
        )

    async def _task_view(self, handle, task):
        record = await self._record(handle, "task", task.task_id)
        return TaskView(
            **snapshot(
                task,
                (
                    "task_id",
                    "goal_id",
                    "title",
                    "description",
                    "status",
                    "priority",
                    "phase",
                    "created_at",
                    "completed_at",
                ),
            ),
            node_id=record["node_id"],
        )

    async def _perform(self, handle, kind, req, data):
        kwargs = {k: v for k, v in data.items() if k not in ("prepared", "scope", "message_ids")}
        if kind == "record_tool_call":
            return ToolCallResponse(
                outcome=self._tool_outcome(await handle.session(req.session_id).observe_tool(data["prepared"]))
            )
        if kind == "record_action":
            result = await handle.record_action(**kwargs)
            return ActionResponse(action_id=data["action_id"], **snapshot(result, ("action_node", "overflow_artifact")))
        if kind == "record_episode":
            return EpisodeResponse(episode_id=data["episode_id"], node_id=await handle.record_episode(**kwargs))
        if kind == "add_observation":
            nid = await handle.add_observation(**kwargs)
            rows = await handle.query(f"MATCH (o:Observation) WHERE id(o) = {nid} RETURN o.observation_id AS oid")
            return ObservationResponse(node_id=nid, observation_id=rows[0]["oid"])
        if kind == "assert_fact":
            return FactResponse(
                **snapshot(
                    await handle.assert_fact(**kwargs), ("fact_id", "node_id", "was_created", "observation_count")
                )
            )
        if kind == "invalidate_fact":
            await handle.invalidate_fact(**kwargs)
            return FactInvalidationResponse(fact_id=req.fact_id, invalidated=True)
        if kind == "consolidate_memory":
            result = await handle.consolidate()
            return ConsolidationResponse(
                cycle=snapshot(
                    result.cycle,
                    (
                        "observations_processed",
                        "facts_created",
                        "facts_reinforced",
                        "facts_invalidated",
                        "drift_alerts",
                    ),
                ),
                procedures=snapshot(result.procedures, ("created", "reinforced", "promoted")),
                topics=snapshot(result.topics, ("created", "updated", "entities_assigned")),
            )
        if kind == "record_procedure_use":
            await handle.record_procedure_use(**kwargs)
            return ProcedureUseResponse(procedure_id=req.procedure_id, recorded=True)
        if kind == "commit_memory_unit":
            result = await handle.session(req.session_id).commit_unit(data["prepared"])
            return MemoryUnitResponse(
                unit_id=data["unit_id"],
                session_id=req.session_id,
                committed=True,
                turns=[self._observe_result(t, mid) for t, mid in zip(result.turns, data["message_ids"])],
            )
        if kind == "create_goal":
            await handle.goals.create(**kwargs)
            return await self._goal_view(handle, await handle.goals.get(data["goal_id"]))
        if kind == "create_task":
            kwargs.pop("depends_on")
            kwargs["priority"] = (
                kwargs.pop("native_priority")
                if req.native_priority is not None
                else kwargs.pop("native_priority") or req.priority
            )
            kwargs["depends_on_task_id"] = req.depends_on[0] if req.depends_on else None
            await handle.goals.create_task(**kwargs)
            task = next(t for t in await handle.goals.tasks() if t.task_id == data["task_id"])
            return await self._task_view(handle, task)
        if kind == "update_goal":
            method = getattr(handle.goals, req.action)
            updated = (
                await method(req.goal_id, result=req.outcome) if req.action == "complete" else await method(req.goal_id)
            )
            goal = await handle.goals.get(req.goal_id) if updated else None
            return GoalStatusResponse(goal_id=req.goal_id, updated=updated, status=goal.status if goal else None)
        if kind == "update_task":
            if req.action in ("abandon", "unblock"):
                updated = await handle.goals.set_task_status(
                    req.task_id, "abandoned" if req.action == "abandon" else "todo"
                )
            else:
                updated = await getattr(handle.goals, req.action + "_task")(req.task_id)
            task = next((t for t in await handle.goals.tasks() if t.task_id == req.task_id), None) if updated else None
            return TaskStatusResponse(task_id=req.task_id, updated=updated, status=task.status if task else None)
        raise ValueError("Unsupported operation")

    async def _replay(self, handle, kind, prior, fingerprint, actor, key):
        if prior["fingerprint"] != fingerprint:
            raise ReceiptConflict("Operation identity conflict")
        if prior["state"] != "completed":
            raise RuntimeError("operation_outcome_unknown")
        if prior["response_type"] not in _RESPONSE_TYPES:
            raise ValueError("Unknown receipt response")
        response = get_class_from_name(prior["response_type"]).model_validate_json(prior["response"])
        if kind == "create_goal":
            await self._owned(handle, "goal", response.goal_id, actor, required=False)
            current = await handle.goals.get(response.goal_id)
            if current:
                response = await self._goal_view(handle, current)
        if kind == "create_task":
            await self._owned(handle, "task", response.task_id, actor, required=False)
            current = next((t for t in await handle.goals.tasks() if t.task_id == response.task_id), None)
            if current:
                response = await self._task_view(handle, current)
        response = response.model_copy(update={"was_replay": True, "actor_id": actor, "operation_id": key})
        return response

    async def _command(self, ctx, uniko, kind, guild_fs=None, request=None, observe_response=False):
        actor = ctx.message.sender.id
        req = request or ctx.payload
        explicit = {
            "create_goal": "goal_id",
            "create_task": "task_id",
            "record_action": "action_id",
            "record_episode": "episode_id",
            "record_tool_call": "call_id",
            "commit_memory_unit": "unit_id",
        }.get(kind)
        key = req.operation_id or (getattr(req, explicit) if explicit else None) or str(ctx.message.id)
        fingerprint = sha256(canonical(req.model_dump(mode="json", exclude={"operation_id"})).encode()).hexdigest()
        info = runtime_info(uniko)
        dispatched = False
        completed = False
        receipts = None
        try:
            if len(canonical(req.model_dump(mode="json")).encode()) > self.config.max_unit_bytes:
                raise ValueError("Command exceeds byte limit")
            async with self._session_lock("*", uniko):
                if info is None:
                    raise ValueError("Managed resolver required")
                receipts = info["runtime"].receipts
                prior = receipts.get(actor, kind, key)
                handle = await self._actor(uniko, actor)
                if kind in ("consolidate_memory", "invalidate_fact", "record_procedure_use"):
                    self._control(ctx)
                if prior:
                    response = await self._replay(handle, kind, prior, fingerprint, actor, key)
                    completed = True
                else:
                    if kind in (
                        "record_tool_call",
                        "record_action",
                        "record_episode",
                    ) and not self._producer_is_allowed(ctx, MemoryRecordKind.EXECUTED_RESULT):
                        raise ValueError("Experience producer rejected")
                    data = await self._preflight(ctx, handle, kind, req, actor, key, guild_fs)
                    # Registration is idempotent and precedes the irreversible command claim.
                    handle = await self._actor(uniko, actor, register=True)
                    prior = receipts.begin(actor, kind, key, fingerprint)
                    if prior is not None:
                        raise RuntimeError("operation_outcome_unknown")
                    dispatched = True
                    response = await self._perform(handle, kind, req, data)
                    response = response.model_copy(update={"actor_id": actor, "operation_id": key})
                    if len(response.model_dump_json().encode()) > self.config.max_structured_output_bytes:
                        raise ValueError("Structured output exceeds byte limit")
                    receipts.finish(actor, kind, key, response)
                    completed = True
            if observe_response:
                result = response.turns[0].model_copy(
                    update={"actor_id": actor, "operation_id": key, "was_replay": response.was_replay}
                )
                ctx.send(result)
            else:
                ctx.send(response)
        except BaseException as exc:
            if dispatched and receipts:
                try:
                    receipts.uncertain(actor, kind, key)
                except Exception:
                    # A durable pending claim already prevents redispatch. Journal
                    # unavailability must not mask the original error/cancellation.
                    logging.getLogger(__name__).warning("Could not persist structured operation uncertainty")
            error = (
                "operation_reply_failed"
                if completed
                else (
                    "operation_outcome_unknown"
                    if dispatched or str(exc) == "operation_outcome_unknown"
                    else (
                        "operation_conflict"
                        if isinstance(exc, ReceiptConflict)
                        else (
                            "unsupported_control"
                            if isinstance(exc, UnsupportedStructuredControl)
                            else "structured_operation_rejected"
                        )
                    )
                )
            )
            self._structured_error(
                ctx,
                MemoryAgentError(
                    error=error,
                    message="The structured memory operation could not be completed.",
                    details={"operation": kind, "operation_id": key},
                ),
            )
            if isinstance(exc, asyncio.CancelledError):
                raise
            if not isinstance(exc, Exception):
                raise

    @agent.processor(GetGoalsRequest, depends_on=["uniko"])
    async def get_goals(self, ctx: ProcessContext[GetGoalsRequest], uniko: uniko.Agent):
        try:
            owner = self._owner(ctx, ctx.payload.owner_id)
            async with self._session_lock("*", uniko):
                handle = await self._actor(uniko, owner)
                goals = (
                    await handle.goals.all()
                    if ctx.payload.phase == "all"
                    else await handle.goals.in_phase(ctx.payload.phase)
                )
                views = []
                for goal in goals:
                    record = await self._record(handle, "goal", goal.goal_id)
                    if record and set(record["owners"]) == {owner}:
                        views.append(await self._goal_view(handle, goal))
                if ctx.payload.parent_goal_id:
                    views = [g for g in views if g.parent_goal_id == ctx.payload.parent_goal_id]
                total = len(views)
                views = views[: ctx.payload.limit or 20]
            ctx.send(GoalsListResponse(goals=views, total_count=total, phase=ctx.payload.phase))
        except Exception:
            self._structured_error(
                ctx, MemoryAgentError(error="get_goals_failed", message="The authorized goals could not be read.")
            )

    @agent.processor(GoalContextRequest, depends_on=["uniko"])
    async def get_goal_context(self, ctx: ProcessContext[GoalContextRequest], uniko: uniko.Agent):
        try:
            owner = self._owner(ctx, ctx.payload.owner_id)
            async with self._session_lock("*", uniko):
                handle = await self._actor(uniko, owner)
                await self._owned(handle, "goal", ctx.payload.goal_id, owner)
                native = await handle.goals.context(ctx.payload.goal_id)
                if native is None:
                    raise ValueError("Goal context missing")
                tasks = []
                if ctx.payload.include_tasks:
                    for task in native.tasks[:100]:
                        await self._owned(handle, "task", task.task_id, owner)
                        tasks.append(await self._task_view(handle, task))
                response = GoalContext(
                    goal=await self._goal_view(handle, native.goal),
                    tasks=tasks,
                    episodes=[],
                    episodes_available=False,
                    recent_messages=[x[:6000] for x in native.recent_messages[:32]],
                    sessions=native.sessions[:32],
                    facts=[x[:6000] for x in native.facts[:100]],
                    entities=[x[:256] for x in native.entities[:100]],
                    progress={},
                )
            ctx.send(response)
        except Exception:
            self._structured_error(
                ctx,
                MemoryAgentError(
                    error="get_goal_context_failed", message="The authorized goal context could not be read."
                ),
            )

    @agent.processor(MemoryOperationStatusRequest, depends_on=["uniko"])
    async def operation_status(self, ctx: ProcessContext[MemoryOperationStatusRequest], uniko: uniko.Agent):
        try:
            async with self._session_lock("*", uniko):
                info = runtime_info(uniko)
                if info is None:
                    raise ValueError("Managed resolver required")
                actor = ctx.message.sender.id
                prior = info["runtime"].receipts.get(actor, ctx.payload.operation, ctx.payload.operation_id)
                state = (
                    "not_found"
                    if prior is None
                    else ("completed" if prior["state"] == "completed" else "outcome_unknown")
                )
            ctx.send(
                MemoryOperationStatus(
                    operation=ctx.payload.operation, operation_id=ctx.payload.operation_id, actor_id=actor, state=state
                )
            )
        except Exception:
            self._structured_error(
                ctx, MemoryAgentError(error="structured_read_failed", message="Operation status could not be read.")
            )

    @agent.processor(MatchProceduresRequest, depends_on=["uniko"])
    async def match_procedures(self, ctx: ProcessContext[MatchProceduresRequest], uniko: uniko.Agent):
        try:
            if len(canonical(ctx.payload.state).encode()) > self.config.max_source_bytes:
                raise ValueError("Procedure state exceeds byte limit")
            async with self._session_lock("*", uniko):
                handle = await self._actor(uniko, ctx.message.sender.id)
                matches = await handle.match_procedures(ctx.payload.state)
            ctx.send(
                ProceduresResponse(
                    procedures=[
                        ProcedureMatch(**snapshot(x, ("procedure_id", "name", "effectiveness")))
                        for x in matches[: ctx.payload.limit]
                    ],
                    truncated=len(matches) > ctx.payload.limit,
                )
            )
        except Exception:
            self._structured_error(
                ctx, MemoryAgentError(error="structured_read_failed", message="Procedures could not be read.")
            )

    async def _rules(self, ctx, uniko, explain=False):
        try:
            async with self._session_lock("*", uniko):
                handle = await self._actor(uniko, ctx.message.sender.id)
                if explain:
                    rule = await handle.explain_rule(ctx.payload.name)
                    rules = [rule] if rule else []
                else:
                    rules = await handle.list_rules()
            limit = 1 if explain else ctx.payload.limit
            budget = ctx.payload.max_characters
            truncated = len(rules) > limit
            views = []
            for rule in rules[:limit]:
                fields = snapshot(rule, ("name", "source_type", "status", "confidence", "source", "natural_language"))
                for name in ("name", "source", "natural_language"):
                    value = fields.get(name)
                    if value:
                        fields[name] = value[:budget]
                        truncated |= len(value) > budget
                        budget -= len(fields[name])
                views.append(MemoryRuleView(**fields))
            ctx.send(MemoryRulesResponse(rules=views, truncated=truncated))
        except Exception:
            self._structured_error(
                ctx, MemoryAgentError(error="structured_read_failed", message="Rules could not be read.")
            )

    @agent.processor(ListMemoryRulesRequest, depends_on=["uniko"])
    async def list_memory_rules(self, ctx: ProcessContext[ListMemoryRulesRequest], uniko: uniko.Agent):
        await self._rules(ctx, uniko)

    @agent.processor(ExplainMemoryRuleRequest, depends_on=["uniko"])
    async def explain_memory_rule(self, ctx: ProcessContext[ExplainMemoryRuleRequest], uniko: uniko.Agent):
        await self._rules(ctx, uniko, explain=True)

    @agent.processor(ReadExperienceRequest, depends_on=["uniko"])
    async def read_experience(self, ctx: ProcessContext[ReadExperienceRequest], uniko: uniko.Agent):
        try:
            req = ctx.payload
            owner = self._owner(ctx, req.owner_id)
            spec = self._authorized_scope(ctx, req.scope)
            async with self._session_lock("*", uniko):
                handle = await self._actor(uniko, owner)
                record = await self._owned(handle, req.kind, req.record_id, owner, required=False)
                if record is None:
                    response = ExperienceResponse(available=False, kind=req.kind, record_id=req.record_id)
                else:
                    await self._scoped(handle, req.kind, req.record_id, spec)
                    label, prop, _ = _RECORDS[req.kind]
                    fields = {
                        "action": (
                            "action_type",
                            "input",
                            "output",
                            "status",
                            "error",
                            "started_at",
                            "ended_at",
                            "tool_name",
                        ),
                        "episode": ("action_type", "outcome", "state", "delta", "importance", "timestamp"),
                        "observation": ("content", "subject", "predicate", "object", "observed_at"),
                        "fact": ("subject", "predicate", "object"),
                        "goal": ("title", "description", "status", "created_at", "completed_at", "guardrails"),
                        "task": ("title", "description", "status", "priority", "created_at", "completed_at"),
                    }[req.kind]
                    rows = await handle.query(
                        f"MATCH (n:{label} {{{prop}: {literal(req.record_id)}}}) RETURN "
                        + ", ".join(f"n.{f} AS {f}" for f in fields)
                    )
                    retained = {}
                    budget = req.max_characters
                    truncated = False
                    for name, value in rows[0].items():
                        # Native query may contain datetime values. Convert them explicitly.
                        if hasattr(value, "isoformat"):
                            value = value.isoformat()
                        size = len(canonical(value))
                        if size > budget:
                            if isinstance(value, str):
                                retained[name] = value[: max(0, budget - 2)]
                            truncated = True
                            budget = 0
                        else:
                            retained[name] = value
                            budget -= size
                    response = ExperienceResponse(
                        available=True, kind=req.kind, record_id=req.record_id, attributes=retained, truncated=truncated
                    )
            ctx.send(response)
        except Exception:
            self._structured_error(
                ctx,
                MemoryAgentError(
                    error="structured_read_failed", message="The authorized experience could not be read."
                ),
            )

    @agent.processor(RecordToolCallRequest, depends_on=["uniko"])
    async def record_tool_call(self, ctx: ProcessContext[RecordToolCallRequest], uniko: uniko.Agent):
        await self._command(ctx, uniko, "record_tool_call")

    @agent.processor(RecordActionRequest, depends_on=["uniko"])
    async def record_action(self, ctx: ProcessContext[RecordActionRequest], uniko: uniko.Agent):
        await self._command(ctx, uniko, "record_action")

    @agent.processor(RecordEpisodeRequest, depends_on=["uniko"])
    async def record_episode(self, ctx: ProcessContext[RecordEpisodeRequest], uniko: uniko.Agent):
        await self._command(ctx, uniko, "record_episode")

    @agent.processor(AddObservationRequest, depends_on=["uniko"])
    async def add_observation(self, ctx: ProcessContext[AddObservationRequest], uniko: uniko.Agent):
        await self._command(ctx, uniko, "add_observation")

    @agent.processor(AssertFactRequest, depends_on=["uniko"])
    async def assert_fact(self, ctx: ProcessContext[AssertFactRequest], uniko: uniko.Agent):
        await self._command(ctx, uniko, "assert_fact")

    @agent.processor(InvalidateFactRequest, depends_on=["uniko"])
    async def invalidate_fact(self, ctx: ProcessContext[InvalidateFactRequest], uniko: uniko.Agent):
        await self._command(ctx, uniko, "invalidate_fact")

    @agent.processor(ConsolidateMemoryRequest, depends_on=["uniko"])
    async def consolidate_memory(self, ctx: ProcessContext[ConsolidateMemoryRequest], uniko: uniko.Agent):
        await self._command(ctx, uniko, "consolidate_memory")

    @agent.processor(RecordProcedureUseRequest, depends_on=["uniko"])
    async def record_procedure_use(self, ctx: ProcessContext[RecordProcedureUseRequest], uniko: uniko.Agent):
        await self._command(ctx, uniko, "record_procedure_use")

    @agent.processor(CreateGoalRequest, depends_on=["uniko"])
    async def create_goal(self, ctx: ProcessContext[CreateGoalRequest], uniko: uniko.Agent):
        await self._command(ctx, uniko, "create_goal")

    @agent.processor(CreateTaskRequest, depends_on=["uniko"])
    async def create_task(self, ctx: ProcessContext[CreateTaskRequest], uniko: uniko.Agent):
        await self._command(ctx, uniko, "create_task")

    @agent.processor(UpdateGoalRequest, depends_on=["uniko"])
    async def update_goal(self, ctx: ProcessContext[UpdateGoalRequest], uniko: uniko.Agent):
        await self._command(ctx, uniko, "update_goal")

    @agent.processor(UpdateTaskRequest, depends_on=["uniko"])
    async def update_task(self, ctx: ProcessContext[UpdateTaskRequest], uniko: uniko.Agent):
        await self._command(ctx, uniko, "update_task")

    @agent.processor(CommitMemoryUnitRequest, depends_on=["uniko", "filesystem:guild_fs:guild"])
    async def commit_memory_unit(
        self, ctx: ProcessContext[CommitMemoryUnitRequest], uniko: uniko.Agent, guild_fs: FileSystem = None
    ):
        await self._command(ctx, uniko, "commit_memory_unit", guild_fs)
