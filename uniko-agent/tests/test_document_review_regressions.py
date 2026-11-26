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
