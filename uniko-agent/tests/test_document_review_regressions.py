"""Regression coverage for workflow admission, deadlines and caller context."""

import asyncio
import threading
import time
import tracemalloc

import pytest
import test_document_coordinator as bus

from rustic_ai.core.guild.agent import ProcessorHelper
from rustic_ai.uniko_agent import (
    DocumentCoordinatorAgent,
    DocumentWorkflowRequest,
    IngestOutcome,
    MemorySource,
)
import rustic_ai.uniko_agent.document_coordinator as coordinator_module

launch = bus.launch


def raw_send(caller, payload, **kwargs):
    caller.publish_dict(
        "requests", payload, format=DocumentWorkflowRequest, routing_slip=caller.guild_spec.routes, **kwargs
    )


@pytest.mark.parametrize("engine", bus.ENGINES)
@pytest.mark.parametrize("blocking", [False, True])
def test_deadline_completes_during_source_read_without_late_ingestion(launch, monkeypatch, engine, blocking):
    started = threading.Event()
    original = coordinator_module.snapshot_document

    async def slow_snapshot(*args):
        started.set()
        if blocking:
            time.sleep(0.4)
        else:
            await asyncio.sleep(0.4)
        return await original(*args)

    monkeypatch.setattr(coordinator_module, "snapshot_document", slow_snapshot)
    _, coordinator, memory, caller = launch(engine=engine, deadline_seconds=0.08)
    publisher = threading.Thread(
        target=bus.send,
        args=(caller, DocumentWorkflowRequest(request_id="slow-read", sources=[MemorySource(text="ok")])),
    )
    publisher.start()
    try:
        assert started.wait(2)
        began = time.monotonic()
        result = bus.terminal(caller, timeout=0.3)
        assert result.error == "document_workflow_timed_out"
        assert time.monotonic() - began < 0.3
        assert not coordinator._workflows
        publisher.join(2)
        assert not publisher.is_alive()
        time.sleep(0.45 if engine == bus.ENGINES[1] else 0.05)
        assert not memory.ingestions
        assert not caller.get_messages()
    finally:
        publisher.join(2)


@pytest.mark.parametrize("engine", bus.ENGINES)
def test_raw_attachment_retry_without_presentation_id_is_identical(launch, engine):
    guild, coordinator, memory, caller = launch(engine=engine)
    filesystem = coordinator._dependency_resolvers["filesystem"].get_or_resolve("document-tests", guild.id, None)
    with filesystem.open("retry.md", "wb") as stream:
        stream.write(b"hold")
    raw = {"request_id": "raw-retry", "sources": [{"media_link": {"url": "retry.md", "on_filesystem": True}}]}
    raw_send(caller, raw)
    bus.wait_for(lambda: memory.ingestions)
    raw_send(caller, raw)
    time.sleep(0.05)
    assert len(memory.ingestions) == 1
    assert not caller.get_messages()
    assert "raw-retry" in coordinator._workflows
    context = memory.ingestions[0]
    context.send(IngestOutcome(record_id=context.payload.record_id, stored=True, searchable=True))
    assert bus.terminal(caller).request_id == "raw-retry"


@pytest.mark.parametrize("active", [False, True])
def test_invalid_request_reuse_has_only_one_terminal_outcome(launch, active):
    _, coordinator, memory, caller = launch()
    request = DocumentWorkflowRequest(request_id="reused", sources=[MemorySource(text="hold" if active else "ok")])
    bus.send(caller, request)
    bus.wait_for(lambda: memory.ingestions)
    if not active:
        assert bus.terminal(caller).request_id == "reused"
    invalid = {"request_id": "reused", "sources": [{"text": "a", "base64_data": "Yg=="}]}
    raw_send(caller, invalid)
    if active:
        assert bus.terminal(caller).error == "request_id_conflict"
        context = memory.ingestions[0]
        context.send(IngestOutcome(record_id=context.payload.record_id, stored=True, searchable=True))
    raw_send(caller, invalid)
    assert not caller.get_messages()
    assert "reused" not in coordinator._workflows
    assert "reused" in coordinator._completed


def test_repeated_invalid_request_is_tombstoned(launch):
    _, _, _, caller = launch()
    raw = {"request_id": "invalid-twice"}
    raw_send(caller, raw)
    assert bus.terminal(caller).error == "document_request_invalid"
    raw_send(caller, raw)
    assert not caller.get_messages()


@pytest.mark.parametrize("text", ["ok", "fail"])
def test_effective_context_survives_without_document_or_history_blobs(launch, monkeypatch, text):
    def before(agent, ctx):
        ctx.update_context({"request_user": "authenticated-user", "correlation": {"id": "trace-123"}})

    monkeypatch.setattr(
        ProcessorHelper, "get_before_fixtures", lambda cls: [before] if cls is DocumentCoordinatorAgent else []
    )
    _, coordinator, memory, caller = launch()
    raw_send(
        caller,
        {"request_id": "compact", "sources": [{"text": text}]},
        session_state={
            "original_attachment": {"file_data": "private document bytes"},
            "history": ["private conversation"],
            "custom_blob": {"data": "x" * 20000},
            "caller_marker": "keep",
        },
    )
    message = bus.wait_for(caller.get_messages)[0]
    for context in (memory.ingestions[0].get_context(), message.session_state):
        assert context["request_user"] == "authenticated-user"
        assert context["correlation"] == {"id": "trace-123"}
        assert context["caller_marker"] == "keep"
        assert not {"original_attachment", "history", "custom_blob"}.intersection(context)
    assert not coordinator._workflows


def test_oversized_inline_source_has_bounded_allocation(launch):
    _, _, memory, caller = launch(max_source_bytes=1, max_workflow_bytes=1)
    request = DocumentWorkflowRequest(request_id="oversized", sources=[MemorySource(text="x" * (8 * 1024 * 1024))])
    tracemalloc.start()
    try:
        bus.send(caller, request)
        assert bus.terminal(caller).error == "document_ingestion_failed"
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    # The transport validates and owns one incoming string. Coordinator
    # preparation must not allocate another full encoded/serialized copy.
    assert peak < 10 * 1024 * 1024
    assert not memory.ingestions


def test_capacity_rejection_precedes_document_hashing(launch, monkeypatch):
    _, _, memory, caller = launch(max_active_workflows=1)
    bus.send(caller, DocumentWorkflowRequest(request_id="active", sources=[MemorySource(text="hold")]))
    bus.wait_for(lambda: memory.ingestions)

    def forbidden(request):
        raise AssertionError("Capacity rejection must not hash document bodies")

    monkeypatch.setattr(coordinator_module, "_fingerprint", forbidden)
    bus.send(caller, DocumentWorkflowRequest(request_id="capacity", sources=[MemorySource(text="x" * 10000)]))
    assert bus.terminal(caller).error == "document_capacity_exceeded"


def test_owned_native_shutdown_drains_accepted_work_on_running_loop(launch):
    from rustic_ai.uniko_agent.resolver import UnikoResolver
    from rustic_ai.uniko_agent.runtime import MemoryRuntime

    class Native:
        def __init__(self):
            self.closed = 0

        async def shutdown(self):
            self.closed += 1

        def shutdown_sync(self):
            raise AssertionError("Event loop cleanup must use the asynchronous native API")

    guild, _, _, _ = launch()
    wrapper = guild.execution_engine.agent_tracker.get_agent_wrapper(guild.id, "memory")
    native = Native()
    runtime = MemoryRuntime(native, False)
    runtime.enter()
    resolver = UnikoResolver()
    resolver._runtimes["accepted"] = runtime
    resolver._uniko_instances["accepted"] = native
    wrapper.agent._owned_dependency_resolvers = (resolver,)

    async def stop():
        cleanup = asyncio.create_task(wrapper.shutdown_async())
        while not runtime.closing:
            await asyncio.sleep(0.005)
        assert runtime.closing
        assert native.closed == 0
        assert not wrapper._shutdown_complete
        runtime.leave()
        await cleanup
        assert wrapper._shutdown_complete
        assert not wrapper._pending_resolvers
        assert not resolver._runtimes
        assert runtime.instance is None
        assert native.closed == 1
        await wrapper.shutdown_async()
        assert native.closed == 1

    asyncio.run(stop())


def test_sync_shutdown_from_temporary_loop_keeps_native_cleanup_alive(launch):
    from rustic_ai.uniko_agent.resolver import UnikoResolver
    from rustic_ai.uniko_agent.runtime import MemoryRuntime

    class Native:
        def __init__(self):
            self.closed = 0

        def shutdown_sync(self):
            self.closed += 1

    guild, _, _, _ = launch()
    wrapper = guild.execution_engine.agent_tracker.get_agent_wrapper(guild.id, "memory")
    native = Native()
    runtime = MemoryRuntime(native, False)
    runtime.enter()
    resolver = UnikoResolver()
    resolver._runtimes["accepted"] = runtime
    resolver._uniko_instances["accepted"] = native
    wrapper.agent._owned_dependency_resolvers = (resolver,)

    async def stop():
        guild.execution_engine.stop_agent(guild.id, "memory")
        assert not wrapper._shutdown_complete
        runtime.leave()
        # Return immediately: temporary-loop shutdown must not cancel cleanup.

    asyncio.run(stop())
    bus.wait_for(lambda: wrapper._shutdown_complete)
    assert native.closed == 1
    assert runtime.instance is None
    assert not resolver._runtimes
    guild.shutdown()
    assert not guild.execution_engine._stopping_wrappers


def test_expired_workflow_cannot_complete_successfully_before_timer_delivery(launch):
    _, coordinator, memory, caller = launch()
    bus.send(caller, DocumentWorkflowRequest(request_id="expired-reply", sources=[MemorySource(text="hold")]))
    bus.wait_for(lambda: memory.ingestions)
    with coordinator._workflow_lock:
        coordinator._workflows["expired-reply"].expires_at = time.monotonic() - 1
    context = memory.ingestions[0]
    context.send(IngestOutcome(record_id=context.payload.record_id, stored=True, searchable=True))
    assert bus.terminal(caller).error == "document_workflow_timed_out"
    assert not coordinator._workflows


def test_anonymous_invalid_request_does_not_reserve_a_valid_request_id(launch):
    _, _, _, caller = launch()
    raw_send(caller, {"sources": [{"text": "ok"}]})
    assert bus.terminal(caller).error == "document_request_invalid"
    bus.send(caller, DocumentWorkflowRequest(request_id="invalid-request", sources=[MemorySource(text="ok")]))
    assert bus.terminal(caller).request_id == "invalid-request"


@pytest.mark.parametrize("engine", bus.ENGINES)
@pytest.mark.parametrize("stage", ["ingest", "recall"])
@pytest.mark.parametrize("pause_at", ["context", "publish"])
def test_delayed_dispatch_cannot_start_native_work_after_terminal_timeout(launch, monkeypatch, engine, stage, pause_at):
    from rustic_ai.uniko_agent import MemoryAgent

    guild, coordinator, memory, caller = launch(native=True, engine=engine, deadline_seconds=0.3)
    native = memory._dependency_resolvers["uniko"].get_or_resolve("document-tests", guild.id, memory.id)
    entered, resume = threading.Event(), threading.Event()
    if pause_at == "context":
        original = coordinator._make_process_context

        def intercept(message, method, *args, **kwargs):
            if any(state.stage == stage for state in coordinator._workflows.values()):
                entered.set()
                assert resume.wait(5)
            return original(message, method, *args, **kwargs)

        monkeypatch.setattr(coordinator, "_make_process_context", intercept)
    else:
        original = coordinator._client.publish

        def intercept_publish(message):
            if (message.session_state or {}).get("document_stage") == stage and message.sender.id == coordinator.id:
                entered.set()
                assert resume.wait(5)
            return original(message)

        monkeypatch.setattr(coordinator._client, "publish", intercept_publish)
    recalls = []
    original_recall = memory._recall

    async def track_recall(*args, **kwargs):
        recalls.append(True)
        return await original_recall(*args, **kwargs)

    monkeypatch.setattr(memory, "_recall", track_recall)
    request = DocumentWorkflowRequest(
        request_id="delayed-dispatch",
        sources=[MemorySource(text="Harbor budget CAD 42000")] if stage == "ingest" else [],
        query="Harbor budget" if stage == "recall" else None,
        require_evidence=False,
    )
    worker = threading.Thread(target=bus.send, args=(caller, request))
    worker.start()
    try:
        assert entered.wait(5)
        result = bus.terminal(caller, 3)
        assert result.error == "document_workflow_timed_out"
        resume.set()
        worker.join(5)
        assert not worker.is_alive()
        time.sleep(0.05)
        assert not coordinator._workflows and not caller.get_messages() and not recalls

        async def artifact_rows():
            return await native.query("MATCH (a:Artifact) RETURN id(a) AS id")

        assert asyncio.run(artifact_rows()) == []
        assert isinstance(memory, MemoryAgent)
    finally:
        resume.set()
        worker.join(5)


@pytest.mark.parametrize("engine", bus.ENGINES)
@pytest.mark.parametrize("timeout_first", [False, True])
@pytest.mark.parametrize("partial", [False, True])
def test_early_reader_timeout_settles_without_losing_usable_siblings(
    launch, monkeypatch, engine, timeout_first, partial
):
    _, coordinator, memory, caller = launch(engine=engine, deadline_seconds=5)
    original = coordinator_module.snapshot_document

    async def early_timeout(source, *args, **kwargs):
        if source.text == "early timeout":
            raise TimeoutError("Reader timeout before workflow deadline")
        return await original(source, *args, **kwargs)

    monkeypatch.setattr(coordinator_module, "snapshot_document", early_timeout)
    sources = [MemorySource(text="Harbor budget CAD 42000"), MemorySource(text="early timeout")]
    if timeout_first:
        sources.reverse()
    started = time.monotonic()
    bus.send(caller, DocumentWorkflowRequest(request_id="reader-timeout", sources=sources, allow_partial=partial))
    result = bus.terminal(caller, 2)
    assert time.monotonic() - started < 2
    assert len(memory.ingestions) == 1
    assert [item.status for item in result.sources] == (
        ["failed", "ingested"] if timeout_first else ["ingested", "failed"]
    )
    failed = next(item for item in result.sources if item.status == "failed")
    assert failed.error == "document_source_timed_out"
    if partial:
        assert isinstance(result, bus.DocumentWorkflowResult) and result.partial
    else:
        assert result.error == "document_ingestion_failed"
    assert not coordinator._workflows and not caller.get_messages()


@pytest.mark.parametrize("engine", bus.ENGINES)
@pytest.mark.parametrize("with_current_sources", [False, True])
def test_source_scoping_filters_unrelated_evidence_before_output_bounds(launch, engine, with_current_sources):
    from rustic_ai.uniko_agent import RecallItem, RecallResponse

    _, coordinator, memory, caller = launch(engine=engine, recall_max_characters=80, recall_token_budget=40)
    sources = [MemorySource(text="Current Harbor document", source_id="current")] if with_current_sources else []
    bus.send(caller, DocumentWorkflowRequest(request_id="source-scope", sources=sources, query="hold"))
    bus.wait_for(lambda: memory.recalls)
    recall = memory.recalls[0]
    allowed = {item.source_id for item in next(iter(coordinator._workflows.values())).sources}
    assert set(recall.payload.scope.sources) == allowed
    old = RecallItem(
        node_id=1,
        kind="Chunk",
        content="OLD CORPUS " * 200,
        score=0.9,
        token_count=600,
        record_kind="external_evidence",
        source_id="old-source",
        source_ids=["old-artifact"],
        sources=[],
    )
    current = old.model_copy(
        update={
            "node_id": 2,
            "content": "CURRENT Harbor budget CAD 85000",
            "token_count": 10,
            "source_id": next(iter(allowed)) if allowed else "another-corpus-source",
        }
    )
    recall.send(
        RecallResponse(items=[old, current], total_tokens=610, phase1_only=False, phase2_only=False, coverage=1.0)
    )
    result = bus.terminal(caller)
    if with_current_sources:
        assert [item.content for item in result.recall.items] == [current.content]
    else:
        assert result.recall.items[0].source_id == "old-source"
    assert result.recall.total_tokens <= 40
    assert not coordinator._workflows and not caller.get_messages()


@pytest.mark.parametrize("engine", bus.ENGINES)
@pytest.mark.parametrize("required", [False, True])
def test_native_unsearchable_current_upload_cannot_recall_older_corpus(launch, engine, required):
    import base64

    _, coordinator, _, caller = launch(native=True, engine=engine)
    bus.send(
        caller,
        DocumentWorkflowRequest(
            request_id="seed-old",
            sources=[MemorySource(text="OLD_CORPUS Harbor budget CAD 42000", source_id="old")],
        ),
    )
    assert bus.terminal(caller, 120).sources[0].outcome.searchable
    bus.send(
        caller,
        DocumentWorkflowRequest(
            request_id="blank-current",
            sources=[
                MemorySource(
                    base64_data=base64.b64encode(bus.blank_pdf()).decode(),
                    path_hint="blank.pdf",
                    mime_type="application/pdf",
                    source_id="current",
                )
            ],
            query="Harbor budget",
            require_evidence=required,
        ),
    )
    result = bus.terminal(caller, 120)
    assert result.sources[0].outcome.stored and not result.sources[0].outcome.searchable
    if required:
        assert result.error == "document_evidence_unavailable"
    else:
        assert isinstance(result, bus.DocumentWorkflowResult) and result.recall.items == []
    bus.send(caller, DocumentWorkflowRequest(request_id="corpus-recall", query="Harbor budget"))
    corpus = bus.terminal(caller, 120)
    assert "OLD_CORPUS" in " ".join(item.content for item in corpus.recall.items)
    assert not coordinator._workflows and not caller.get_messages()


@pytest.mark.parametrize("engine", bus.ENGINES)
def test_native_partial_current_sources_keep_old_corpus_out_of_evidence(launch, engine):
    import base64

    _, coordinator, _, caller = launch(native=True, engine=engine)
    bus.send(
        caller,
        DocumentWorkflowRequest(
            request_id="seed-old",
            sources=[MemorySource(text="OLD_CORPUS Harbor budget CAD 42000", source_id="old")],
        ),
    )
    bus.terminal(caller, 120)
    bus.send(
        caller,
        DocumentWorkflowRequest(
            request_id="current-partial",
            query="Harbor budget",
            allow_partial=True,
            sources=[
                MemorySource(text="CURRENT_UPLOAD Harbor budget CAD 85000", source_id="current"),
                MemorySource(
                    base64_data=base64.b64encode(bus.blank_pdf()).decode(),
                    path_hint="blank.pdf",
                    mime_type="application/pdf",
                    source_id="blank",
                ),
            ],
        ),
    )
    result = bus.terminal(caller, 120)
    assert result.sources[0].outcome.searchable and not result.sources[1].outcome.searchable
    content = " ".join(item.content for item in result.recall.items)
    assert "CURRENT_UPLOAD" in content and "OLD_CORPUS" not in content
    assert all(item.source_id == result.sources[0].source_id for item in result.recall.items)
    assert not coordinator._workflows and not caller.get_messages()


@pytest.mark.parametrize("protocol", ["ingest", "recall"])
@pytest.mark.parametrize("deadline", [None, True, "9999999999999", 1.5, 0])
def test_invalid_deadline_is_rejected_by_wrapper_before_dependency_resolution(
    memory_test_harness, monkeypatch, protocol, deadline
):
    from rustic_ai.core.messaging.core.message import AgentTag, Message
    from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
    from rustic_ai.core.utils.gemstone_id import GemstoneID
    from rustic_ai.uniko_agent import IngestDocumentRequest, MemoryScope, RecallRequest

    memory = memory_test_harness.agent

    def forbidden(*args, **kwargs):
        raise AssertionError("Expired or malformed workflow must not build a dependency context")

    monkeypatch.setattr(memory, "_make_process_context", forbidden)
    request = (
        IngestDocumentRequest(record_id="deadline", session_id="corpus", source=MemorySource(text="Harbor"))
        if protocol == "ingest"
        else RecallRequest(
            query="Harbor", scope=MemoryScope(sessions=["corpus"]), allowed_record_kinds=["external_evidence"]
        )
    )
    memory._on_message(
        Message(
            id_obj=GemstoneID.from_int(9713724488973030400),
            sender=AgentTag(id="test"),
            topics=["default"],
            format=get_qualified_class_name(type(request)),
            payload=request.model_dump(mode="json"),
            session_state={"document_deadline_ms": deadline},
        )
    )
    assert not memory_test_harness.get_sent_messages()


@pytest.mark.parametrize("engine", bus.ENGINES)
@pytest.mark.parametrize("with_deadline", [False, True])
def test_direct_memory_requests_preserve_missing_and_future_deadline_behavior(
    launch, monkeypatch, engine, with_deadline
):
    from rustic_ai.uniko_agent import IngestDocumentRequest, MemoryScope, RecallRequest

    guild, coordinator, memory, caller = launch(native=True, engine=engine)
    memory.config.allowed_record_producers = {"external_evidence": ["caller"]}
    memory.config.scope_producers = ["caller"]
    native = memory._dependency_resolvers["uniko"].get_or_resolve("document-tests", guild.id, memory.id)

    async def artifact_rows():
        return await native.query("MATCH (a:Artifact) RETURN id(a) AS id")

    context = {"document_deadline_ms": int((time.time() + 30) * 1000)} if with_deadline else {}
    request = IngestDocumentRequest(
        record_id="direct", session_id="corpus:references", source=MemorySource(text="Harbor budget CAD 42000")
    )
    caller.publish_dict(
        "commands",
        request.model_dump(mode="json"),
        format=type(request),
        routing_slip=caller.guild_spec.routes,
        session_state=context,
    )
    assert bus.wait_for(lambda: asyncio.run(artifact_rows()))
    completed = threading.Event()
    original = memory._recall

    async def track_recall(*args, **kwargs):
        response = await original(*args, **kwargs)
        completed.set()
        return response

    monkeypatch.setattr(memory, "_recall", track_recall)
    caller.publish_dict(
        "commands",
        RecallRequest(
            query="Harbor budget",
            scope=MemoryScope(sessions=["corpus:references"]),
            allowed_record_kinds=["external_evidence"],
        ).model_dump(mode="json"),
        format=RecallRequest,
        routing_slip=caller.guild_spec.routes,
        session_state=context,
    )
    assert completed.wait(5)
    assert len(asyncio.run(artifact_rows())) == 1
    assert not coordinator._workflows and not caller.get_messages()
