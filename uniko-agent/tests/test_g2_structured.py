"""Native graph, authenticated ownership, and restart-safe G2 regressions."""

from types import SimpleNamespace

import pytest

from rustic_ai.uniko_agent import (
    AddObservationRequest,
    AssertFactRequest,
    CommitMemoryUnitRequest,
    CreateGoalRequest,
    CreateTaskRequest,
    GetGoalsRequest,
    GoalContextRequest,
    InvalidateFactRequest,
    MemoryAgent,
    MemoryAgentConfig,
    MemoryScope,
    ObserveTurnRequest,
    ReadExperienceRequest,
    RecordActionRequest,
    RecordEpisodeRequest,
    RecordToolCallRequest,
    ToolCallSpec,
    UnikoResolver,
    UpdateGoalRequest,
    UpdateTaskRequest,
)
from rustic_ai.uniko_agent.receipts import ReceiptStore
from rustic_ai.uniko_agent.resolver import runtime_info


def memory(config=None):
    value = MemoryAgent.__new__(MemoryAgent)
    value.config = config or MemoryAgentConfig(control_producers=["reporter"])
    value.guild_spec = SimpleNamespace(id="g2-guild")
    return value


def context(payload, sender="reporter", key="command"):
    sent: list = []
    errors: list = []
    return SimpleNamespace(
        payload=payload,
        get_context=lambda: {},
        message=SimpleNamespace(id=key, sender=SimpleNamespace(id=sender)),
        send=sent.append,
        send_error=errors.append,
        sent=sent,
        errors=errors,
        agent=SimpleNamespace(guild_id="g2-guild"),
    )


@pytest.fixture
async def native():
    resolver = UnikoResolver(storage_path=None, streaming=False)
    handle = resolver.get_or_resolve("org", "g2", "memory")
    yield handle
    await resolver.shutdown_async()


async def invoke(agent, handle, method, request, sender="reporter", key="command"):
    ctx = context(request, sender, key)
    await getattr(MemoryAgent, method).__wfn__(agent, ctx, handle)
    return ctx


@pytest.mark.asyncio
async def test_goal_task_bootstrap_real_ids_ownership_and_replays(native):
    agent = memory()
    created = await invoke(
        agent,
        native,
        "create_goal",
        CreateGoalRequest(title="Investigate", guardrails=["Use evidence"], metrics={"coverage": 1}),
    )
    assert not created.errors
    goal = created.sent[0]
    assert goal.goal_id.startswith("rustic-create_goal-")
    assert goal.node_id is not None
    assert goal.guardrails == ["Use evidence"] and goal.metrics == {"coverage": 1}
    rows = await native.query("MATCH (g:Goal)-[:OWNED_BY]->(p:Participant) RETURN p.participant_id AS owner")
    assert rows == [{"owner": "reporter"}]
    assert not await native.query("MATCH (m:Message) RETURN id(m) AS id")
    task_ctx = await invoke(
        agent,
        native,
        "create_task",
        CreateTaskRequest(title="Search", goal_id=goal.goal_id, native_priority=0.7),
        key="task",
    )
    assert not task_ctx.errors
    task = task_ctx.sent[0]
    assert task.priority == 0.7 and task.status == "todo"
    started = await invoke(
        agent, native, "update_task", UpdateTaskRequest(task_id=task.task_id, action="start"), key="start"
    )
    assert not started.errors and started.sent[0].updated
    replay = await invoke(
        agent,
        native,
        "create_task",
        CreateTaskRequest(title="Search", goal_id=goal.goal_id, native_priority=0.7),
        key="task",
    )
    assert replay.sent[0].was_replay and replay.sent[0].status == started.sent[0].status
    foreign = await invoke(
        agent,
        native,
        "update_goal",
        UpdateGoalRequest(goal_id=goal.goal_id, action="abandon"),
        sender="stranger",
        key="foreign",
    )
    assert foreign.errors and not foreign.sent
    listed = await invoke(agent, native, "get_goals", GetGoalsRequest(), sender="stranger")
    assert listed.sent[0].goals == []
    missing = await invoke(
        agent, native, "update_task", UpdateTaskRequest(task_id="absent", action="complete"), key="missing"
    )
    assert missing.sent[0].updated is False and missing.sent[0].status is None
    bad = await invoke(
        agent,
        native,
        "update_task",
        UpdateTaskRequest(task_id=task.task_id, action="complete", outcome="ignored?"),
        key="unsupported",
    )
    assert bad.errors and not bad.sent
    detail = await invoke(agent, native, "get_goal_context", GoalContextRequest(goal_id=goal.goal_id))
    assert not detail.errors and not detail.sent[0].episodes_available and detail.sent[0].episodes == []


@pytest.mark.asyncio
async def test_native_tools_actions_episodes_observations_and_facts(native):
    agent = memory()
    unit = CommitMemoryUnitRequest(
        session_id="research",
        unit_id="unit-a",
        turns=[
            ObserveTurnRequest(
                sender_id="reported-user",
                message_id="msg",
                content="The evidence supports a blue sky.",
            ),
            ObserveTurnRequest(
                sender_id="reporter",
                message_id="tool-turn",
                content="Tool search completed.",
                tool_calls=[
                    ToolCallSpec(
                        tool_name="search",
                        call_id="search-1",
                        arguments={"q": "sky"},
                        json_output={"color": "blue"},
                        triggered_by="msg",
                        status="success",
                    )
                ],
            ),
        ],
    )
    stored = await invoke(agent, native, "commit_memory_unit", unit)
    assert not stored.errors
    assert stored.sent[0].turns[1].tool_calls[0].call_id == "search-1"
    owners = await native.query(
        "MATCH (a:Action {action_id:'search-1'})-[:PERFORMED_BY]->(p:Participant) RETURN p.participant_id AS owner"
    )
    assert owners == [{"owner": "reporter"}]
    assert (await native.data.message("msg")).sender_id == "reported-user"
    forged = CommitMemoryUnitRequest(
        session_id="research",
        unit_id="forged",
        turns=[
            ObserveTurnRequest(
                sender_id="reported-user",
                message_id="forged-msg",
                content="Do not store",
                tool_calls=[ToolCallSpec(tool_name="search", call_id="forged-call", text_output="data")],
            )
        ],
    )
    denied = await invoke(agent, native, "commit_memory_unit", forged)
    assert denied.errors[0].error == "unsupported_control"
    assert await native.data.message("forged-msg") is None
    replay = await invoke(agent, native, "commit_memory_unit", unit, key="other-envelope")
    assert replay.sent[0].was_replay
    conflict = await invoke(
        agent,
        native,
        "record_tool_call",
        RecordToolCallRequest(
            session_id="research",
            tool_name="search",
            call_id="search-1",
            arguments={"q": "other"},
            json_output={"color": "blue"},
        ),
    )
    assert conflict.errors[0].error == "operation_conflict"
    action = await invoke(
        agent,
        native,
        "record_action",
        RecordActionRequest(
            action_type="compare",
            action_id="compare",
            previous_action_id="search-1",
            triggered_by_message_id="msg",
            output={"accepted": True},
        ),
    )
    assert not action.errors
    episode = await invoke(
        agent,
        native,
        "record_episode",
        RecordEpisodeRequest(
            action_type="investigate", episode_id="ep", outcome="success", involved_action_ids=["compare"]
        ),
    )
    assert not episode.errors
    rows = await native.query("MATCH (e:Episode)-[:INVOLVES]->(a:Action) RETURN a.action_id AS aid")
    assert rows == [{"aid": "compare"}]
    observation = await invoke(
        agent,
        native,
        "add_observation",
        AddObservationRequest(
            message_id="msg",
            content="Sky is blue",
            subject="Sky",
            predicate="color",
            object="blue",
            scope=MemoryScope(sessions=["research"]),
        ),
        key="obs",
    )
    assert not observation.errors
    oid = observation.sent[0].observation_id
    assert oid != str(observation.sent[0].node_id)
    fact = await invoke(
        agent,
        native,
        "assert_fact",
        AssertFactRequest(
            subject="Sky",
            predicate="color",
            object="blue",
            supporting_observation_ids=[oid],
            scope=MemoryScope(sessions=["research"]),
        ),
        key="fact",
    )
    assert not fact.errors
    links = await native.query("MATCH (f:Fact)-[:SUPPORTED_BY]->(o:Observation) RETURN o.observation_id AS oid")
    assert any(r["oid"] == oid for r in links)
    read = await invoke(
        agent,
        native,
        "read_experience",
        ReadExperienceRequest(kind="episode", record_id="ep", scope=MemoryScope(sessions=None), max_characters=10),
    )
    assert not read.errors and read.sent[0].truncated
    invalidated = await invoke(
        agent,
        native,
        "invalidate_fact",
        InvalidateFactRequest(fact_id=fact.sent[0].fact_id, scope=MemoryScope(sessions=None)),
        key="invalidate",
    )
    assert not invalidated.errors


@pytest.mark.asyncio
async def test_preparation_failures_and_unknown_effect_never_retry(native, tmp_path):
    agent = memory(MemoryAgentConfig(max_unit_bytes=200, control_producers=["reporter"]))
    unit = CommitMemoryUnitRequest(
        session_id="s", turns=[ObserveTurnRequest(sender_id="reporter", message_id="must-not-exist", content="x" * 300)]
    )
    rejected = await invoke(agent, native, "commit_memory_unit", unit)
    assert rejected.errors[0].error == "structured_operation_rejected"
    assert await native.data.message("must-not-exist") is None
    agent.config = MemoryAgentConfig()
    runtime = runtime_info(native)["runtime"]
    runtime.receipts.close()
    path = str(tmp_path / "receipts.sqlite3")
    runtime.receipts = ReceiptStore(path)
    real_finish = runtime.receipts.finish

    def fail_finish(*args):
        raise OSError("simulated crash after native commit")

    runtime.receipts.finish = fail_finish
    request = RecordEpisodeRequest(action_type="finished", episode_id="durable")
    failed = await invoke(agent, native, "record_episode", request)
    assert failed.errors[0].error == "operation_outcome_unknown"
    runtime.receipts.finish = real_finish
    runtime.receipts.close()
    runtime.receipts = ReceiptStore(path)
    retry = await invoke(agent, native, "record_episode", request, key="different-delivery")
    assert retry.errors[0].error == "operation_outcome_unknown"
    assert len(await native.query("MATCH (e:Episode {episode_id:'durable'}) RETURN id(e) AS id")) == 1
    assert not await native.query("MATCH (e:Episode {episode_id:'durable'})-[:FOLLOWED_BY]->(e) RETURN id(e) AS id")


@pytest.mark.asyncio
async def test_native_procedure_learning_feedback_replay_and_rules(native):
    from datetime import datetime, timedelta, timezone

    from rustic_ai.uniko_agent import (
        ConsolidateMemoryRequest,
        ExplainMemoryRuleRequest,
        ListMemoryRulesRequest,
        MatchProceduresRequest,
        MemoryOperationStatusRequest,
        RecordProcedureUseRequest,
    )

    agent = memory()
    base = datetime.now(timezone.utc) - timedelta(hours=2)
    for i in range(3):
        for offset, action in ((0, "scan"), (30, "report")):
            request = RecordEpisodeRequest(
                action_type=action,
                episode_id=f"e-{i}-{action}",
                outcome="success",
                timestamp=base + timedelta(minutes=5 * i, seconds=offset),
                state={"topic": action},
            )
            result = await invoke(agent, native, "record_episode", request)
            assert not result.errors
    consolidated = await invoke(agent, native, "consolidate_memory", ConsolidateMemoryRequest(operation_id="cycle"))
    assert not consolidated.errors and consolidated.sent[0].procedures["created"] >= 1
    matched = await invoke(
        agent, native, "match_procedures", MatchProceduresRequest(state={"last_action_type": "scan"})
    )
    assert not matched.errors
    procedure = next(p for p in matched.sent[0].procedures if p.name == "scan → report")
    request = RecordProcedureUseRequest(procedure_id=procedure.procedure_id, succeeded=True, operation_id="feedback")
    first = await invoke(agent, native, "record_procedure_use", request)
    assert not first.errors
    before = await native.query("MATCH (p:Procedure) RETURN p.success_count AS successes")
    retry = await invoke(agent, native, "record_procedure_use", request, key="retry")
    assert retry.sent[0].was_replay
    assert before == await native.query("MATCH (p:Procedure) RETURN p.success_count AS successes")
    status = await invoke(
        agent,
        native,
        "operation_status",
        MemoryOperationStatusRequest(operation="record_procedure_use", operation_id="feedback"),
    )
    assert status.sent[0].state == "completed"
    denied = await invoke(agent, native, "record_procedure_use", request, sender="stranger")
    assert denied.errors
    rules = await invoke(agent, native, "list_memory_rules", ListMemoryRulesRequest(limit=1, max_characters=20))
    assert not rules.errors and len(rules.sent[0].rules) <= 1
    missing_rule = await invoke(agent, native, "explain_memory_rule", ExplainMemoryRuleRequest(name="no-such-rule"))
    assert missing_rule.sent[0].rules == []


@pytest.mark.asyncio
async def test_goal_and_receipt_survive_actual_resolver_restart(tmp_path):
    from rustic_ai.core.guild.dsl import DependencySpec

    def resolver():
        value = UnikoResolver(storage_path="memory", streaming=False)
        value.set_dependency_specs(
            {
                "filesystem": DependencySpec(
                    class_name="rustic_ai.core.guild.agent_ext.depends.filesystem.FileSystemResolver",
                    properties={
                        "path_base": str(tmp_path),
                        "protocol": "file",
                        "storage_options": {"auto_mkdir": True},
                    },
                )
            }
        )
        return value

    agent = memory()
    first = resolver()
    handle = first.get_or_resolve("org", "guild", "memory")
    request = CreateGoalRequest(title="Persistent objective", operation_id="create")
    result = await invoke(agent, handle, "create_goal", request)
    assert not result.errors
    gid = result.sent[0].goal_id
    unit = CommitMemoryUnitRequest(
        session_id="persistent",
        unit_id="restart-unit",
        turns=[
            ObserveTurnRequest(
                sender_id="reporter",
                message_id="restart-message",
                content="Project is ready.",
                tool_calls=[ToolCallSpec(tool_name="check", call_id="restart-call", text_output="ready")],
            )
        ],
    )
    stored = await invoke(agent, handle, "commit_memory_unit", unit)
    assert not stored.errors
    episode = await invoke(
        agent,
        handle,
        "record_episode",
        RecordEpisodeRequest(
            action_type="check", episode_id="restart-episode", outcome="success", involved_action_ids=["restart-call"]
        ),
    )
    assert not episode.errors
    observation = await invoke(
        agent,
        handle,
        "add_observation",
        AddObservationRequest(
            message_id="restart-message",
            content="Project is ready",
            subject="Project",
            predicate="state",
            object="ready",
            scope=MemoryScope(sessions=["persistent"]),
        ),
        key="restart-observation",
    )
    assert not observation.errors
    fact = await invoke(
        agent,
        handle,
        "assert_fact",
        AssertFactRequest(
            subject="Project",
            predicate="state",
            object="ready",
            supporting_observation_ids=[observation.sent[0].observation_id],
            scope=MemoryScope(sessions=["persistent"]),
        ),
        key="restart-fact",
    )
    assert not fact.errors
    fid = fact.sent[0].fact_id
    await first.shutdown_async()
    second = resolver()
    handle = second.get_or_resolve("org", "guild", "memory")
    try:
        replay = await invoke(agent, handle, "create_goal", request, key="restart")
        assert not replay.errors and replay.sent[0].was_replay and replay.sent[0].goal_id == gid
        repeated = await invoke(agent, handle, "commit_memory_unit", unit)
        assert not repeated.errors and repeated.sent[0].was_replay
        assert repeated.sent[0].turns[0].message_id == "restart-message"
        assert repeated.sent[0].turns[0].tool_calls[0].call_id == "restart-call"
        edges = await handle.query(
            "MATCH (e:Episode {episode_id:'restart-episode'})-[:INVOLVES]->(a:Action) RETURN a.action_id AS aid"
        )
        assert edges == [{"aid": "restart-call"}]
        persisted = await invoke(
            agent,
            handle,
            "read_experience",
            ReadExperienceRequest(kind="fact", record_id=fid, scope=MemoryScope(sessions=None)),
        )
        assert not persisted.errors and persisted.sent[0].attributes["object"] == "ready"
        complete = await invoke(
            agent,
            handle,
            "update_goal",
            UpdateGoalRequest(goal_id=gid, action="complete", outcome="done"),
            key="complete",
        )
        assert complete.sent[0].updated and complete.sent[0].status == "done"
    finally:
        await second.shutdown_async()


def test_tool_output_serialization_and_unsupported_controls():
    from pydantic import ValidationError

    for spec in (
        ToolCallSpec(tool_name="text", text_output="hello"),
        ToolCallSpec(tool_name="null", json_output=None),
        ToolCallSpec(tool_name="none"),
        ToolCallSpec(tool_name="bytes", base64_output="eA==", mime_type="text/plain"),
    ):
        assert ToolCallSpec.model_validate(spec.model_dump(mode="json")) == spec
    with pytest.raises(ValidationError):
        UpdateGoalRequest(goal_id="g", action="pause")
    with pytest.raises(ValidationError):
        CreateTaskRequest(goal_id="g", title="t", depends_on=["a", "b"])
    with pytest.raises(ValidationError):
        CreateTaskRequest(goal_id="g", title="t", priority=3, native_priority=0.1)


@pytest.mark.asyncio
async def test_cancellation_after_native_effect_is_unknown_and_releases_gate(native, monkeypatch):
    import asyncio

    agent = memory()
    real_perform = agent._perform

    async def interrupted(*args):
        await real_perform(*args)
        raise asyncio.CancelledError()

    monkeypatch.setattr(agent, "_perform", interrupted)
    request = RecordEpisodeRequest(action_type="cancelled", episode_id="cancelled-effect")
    ctx = context(request)
    with pytest.raises(asyncio.CancelledError):
        await MemoryAgent.record_episode.__wfn__(agent, ctx, native)
    assert len(ctx.errors) == 1 and ctx.errors[0].error == "operation_outcome_unknown"
    assert not agent._operation_gate.lock.locked()
    monkeypatch.setattr(agent, "_perform", real_perform)
    repeated = await invoke(agent, native, "record_episode", request)
    assert repeated.errors[0].error == "operation_outcome_unknown"
    assert len(await native.query("MATCH (e:Episode {episode_id:'cancelled-effect'}) RETURN id(e) AS nid")) == 1


@pytest.mark.asyncio
async def test_unit_attachment_preflight(native):
    from rustic_ai.uniko_agent import MemorySource

    agent = memory()
    bad = CommitMemoryUnitRequest(
        session_id="s",
        unit_id="bad",
        turns=[
            ObserveTurnRequest(sender_id="reporter", message_id="first", content="Should not commit"),
            ObserveTurnRequest(
                sender_id="reporter",
                message_id="second",
                content="Invalid bytes",
                attachments=[MemorySource(base64_data="not base64!")],
            ),
        ],
    )
    result = await invoke(agent, native, "commit_memory_unit", bad)
    assert result.errors[0].error == "structured_operation_rejected"
    assert await native.data.message("first") is None and await native.data.message("second") is None
    small = memory(MemoryAgentConfig(max_source_bytes=8, max_unit_bytes=1000))
    oversized = CommitMemoryUnitRequest(
        session_id="s",
        unit_id="large",
        turns=[
            ObserveTurnRequest(
                sender_id="reporter", message_id="large", content="Attachment", attachments=[MemorySource(text="x" * 9)]
            )
        ],
    )
    result = await invoke(small, native, "commit_memory_unit", oversized)
    assert result.errors and await native.data.message("large") is None


@pytest.mark.asyncio
async def test_creation_replay_rechecks_native_ownership(native):
    agent = memory()
    request = CreateGoalRequest(title="Owned objective", goal_id="receipt-owned")
    created = await invoke(agent, native, "create_goal", request)
    assert not created.errors
    other = await agent._actor(native, "other", register=True)
    # A native caller can merge the same ID and add a foreign owner. The public
    # wrapper must not disclose that current view through an older receipt.
    await other.goals.create("Foreign title", goal_id="receipt-owned")
    replay = await invoke(agent, native, "create_goal", request, key="retry")
    assert not replay.sent and replay.errors[0].error == "structured_operation_rejected"


@pytest.mark.parametrize("priority", [None, 0.0, 0.7, 1.0])
def test_task_priority_survives_delivery_serialization(priority):
    request = CreateTaskRequest(goal_id="g", title="t", native_priority=priority)
    restored = CreateTaskRequest.model_validate(request.model_dump(mode="json"))
    assert restored == request
    assert restored.priority == (3 if priority is None else None)
    assert restored.native_priority == priority


@pytest.mark.asyncio
async def test_goal_listing_filters_conflicting_native_owners(native):
    agent = memory()
    for goal_id in ("clean-goal", "conflicted-goal"):
        result = await invoke(agent, native, "create_goal", CreateGoalRequest(title="Owned", goal_id=goal_id))
        assert not result.errors
    other = await agent._actor(native, "other", register=True)
    await other.goals.create("Foreign title", goal_id="conflicted-goal")
    for phase in ("all", "active"):
        result = await invoke(agent, native, "get_goals", GetGoalsRequest(phase=phase))
        assert not result.errors
        assert result.sent[0].total_count == 1
        assert [goal.goal_id for goal in result.sent[0].goals] == ["clean-goal"]
        assert "Foreign title" not in result.sent[0].model_dump_json()


@pytest.mark.asyncio
@pytest.mark.parametrize("cancelled", [False, True])
async def test_uncertainty_journal_failure_preserves_terminal_error(native, monkeypatch, cancelled):
    import asyncio
    import sqlite3

    agent = memory()
    receipts = runtime_info(native)["runtime"].receipts
    original_cancel = asyncio.CancelledError("original native cancellation")
    real_perform = agent._perform

    async def interrupted(*args):
        await real_perform(*args)
        raise original_cancel

    def journal_failure(*args):
        raise sqlite3.OperationalError("journal unavailable")

    monkeypatch.setattr(receipts, "finish", journal_failure)
    monkeypatch.setattr(receipts, "uncertain", journal_failure)
    if cancelled:
        monkeypatch.setattr(agent, "_perform", interrupted)
    request = RecordEpisodeRequest(action_type="journal-failure", episode_id="journal-effect")
    ctx = context(request)
    if cancelled:
        with pytest.raises(asyncio.CancelledError) as caught:
            await MemoryAgent.record_episode.__wfn__(agent, ctx, native)
        assert caught.value is original_cancel
    else:
        await MemoryAgent.record_episode.__wfn__(agent, ctx, native)
    assert not ctx.sent and len(ctx.errors) == 1
    assert ctx.errors[0].error == "operation_outcome_unknown"
    assert ctx.errors[0].details == {"operation": "record_episode", "operation_id": "journal-effect"}
    assert not agent._operation_gate.lock.locked()
    assert receipts.get("reporter", "record_episode", "journal-effect")["state"] == "pending"
    monkeypatch.setattr(agent, "_perform", real_perform)
    repeated = await invoke(agent, native, "record_episode", request)
    assert len(repeated.errors) == 1 and repeated.errors[0].error == "operation_outcome_unknown"
    assert len(await native.query("MATCH (e:Episode {episode_id:'journal-effect'}) RETURN id(e) AS nid")) == 1


@pytest.mark.asyncio
async def test_batch_cancel_preserves_committed_item_uncertainty(monkeypatch):
    import asyncio

    from rustic_ai.uniko_agent import BatchSubmitRequest

    resolver = UnikoResolver(storage_path=None, streaming=True)
    native = resolver.get_or_resolve("org", "g2-batch", "memory")
    try:
        agent = memory()
        real_perform = agent._perform

        async def interrupted(*args):
            await real_perform(*args)
            raise asyncio.CancelledError()

        monkeypatch.setattr(agent, "_perform", interrupted)
        request = BatchSubmitRequest(
            batch_id="cancel-batch",
            session_id="s",
            flush_after=False,
            turns=[
                {
                    "sender_id": "reporter",
                    "content": "Committed tool result",
                    "tool_calls": [{"tool_name": "search", "call_id": "cancel-call", "text_output": "data"}],
                },
                {"sender_id": "reporter", "content": "Never started"},
            ],
        )
        ctx = context(request)
        with pytest.raises(asyncio.CancelledError):
            await MemoryAgent.batch_submit.__wfn__(agent, ctx, native)
        assert not ctx.errors and len(ctx.sent) == 3
        current, unstarted, summary = ctx.sent
        assert current.message_id == "batch-cancel-batch:0"
        assert current.stored is None and current.error == "operation_outcome_unknown"
        assert current.operation == "commit_memory_unit" and current.operation_id == current.message_id
        assert unstarted.message_id == "batch-cancel-batch:1"
        assert unstarted.stored is False and unstarted.error == "cancelled"
        assert unstarted.operation_id is None
        assert summary.outcomes == [current, unstarted]
        assert summary.submitted_count == 0 and summary.uncertain_count == 1
        assert summary.error == "operation_outcome_unknown" and not summary.flushed
        assert await native.data.message(current.message_id) is not None
        assert await native.data.message(unstarted.message_id) is None
        assert len(await native.query("MATCH (a:Action {action_id:'cancel-call'}) RETURN id(a) AS nid")) == 1
        receipts = runtime_info(native)["runtime"].receipts
        assert receipts.get("reporter", current.operation, current.operation_id)["state"] == "outcome_unknown"
        monkeypatch.setattr(agent, "_perform", real_perform)
        retry = context(request)
        await MemoryAgent.batch_submit.__wfn__(agent, retry, native)
        assert retry.sent[0].stored is None and retry.sent[0].operation_id == current.operation_id
        assert retry.sent[-1].uncertain_count == 1 and retry.sent[-1].submitted_count == 1
        assert len(await native.query("MATCH (a:Action {action_id:'cancel-call'}) RETURN id(a) AS nid")) == 1
    finally:
        await resolver.shutdown_async()
