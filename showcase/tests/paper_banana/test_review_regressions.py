"""Regression coverage for Phase 2 transport, readiness and dispatch review."""

import asyncio
import json
import threading
import time
from urllib.parse import quote

import pytest
import test_paper_banana as harness

from rustic_ai.showcase.paper_banana_sources import (
    AcquiredUpload,
    HttpUploadSourceReader,
)
from rustic_ai.uniko_agent import compact_document_context
from rustic_ai.uniko_agent.integration import read_source_bytes

launch = harness.launch


@pytest.mark.parametrize("transport", ["api", "file", "absolute"])
def test_studio_and_filesystem_transport_references(launch, transport):
    guild, _, _, caller, fs, _, _ = launch(proxy=True)
    name = "Harbor reference #1.md"
    harness.write(fs, name)
    if transport == "api":
        url = f"/rustic/api/guilds/{guild.id}/files/{quote(name)}"
    elif transport == "file":
        url = "file:///" + quote(name)
    else:
        url = fs.path + "/" + name
    # The unaddressed user proxy shape matches a Studio upload reply.
    payload = harness.file_request("Draw Harbor", (url,))
    payload["messages"][0]["content"][0]["file_url"] = {
        "guild_id": guild.id,
        "url": url,
        "filename": name,
        "content_type": "text/plain",
        "content_length": 34,
        "on_filesystem": True,
    }
    inner = harness.Message(
        id_obj=caller._generate_id(harness.Priority.NORMAL),
        topics="default_topic",
        sender=caller.get_agent_tag(),
        format=harness.get_qualified_class_name(harness.ChatCompletionRequest),
        payload=payload,
    )
    caller.publish(harness.UserProxyAgent.get_user_inbox_topic("researcher"), inner)
    messages = harness.wait(lambda: [m for m in caller.get_messages() if m.process_status in {"completed", "error"}])
    assert len(messages) == 1 and messages[0].process_status == "completed"
    terminal = [
        m for m in harness.instance(guild, "trace_probe").get_messages() if m.format.endswith("PaperBananaResult")
    ][-1]
    assert terminal.payload["sources"][0]["name"] == name
    assert terminal.payload["sources"][0]["mime_type"] == "text/plain"


@pytest.mark.parametrize(
    "url",
    [
        "/rustic/api/guilds/foreign/files/reference.md",
        "/rustic/api/guilds/current/files/%2e%2e/outside.md",
        "/rustic/api/guilds/current/files/%2foutside.md",
        "file:///../outside.md",
        "file://other-host/reference.md",
        "/outside/reference.md",
    ],
)
def test_transport_resolution_rejects_foreign_guild_and_traversal(url):
    with pytest.raises(ValueError):
        HttpUploadSourceReader([]).staged_path(url, "current", "/private/guild")


@pytest.mark.parametrize("engine", harness.ENGINES)
def test_native_deduplicated_pdf_readiness_and_reopen(launch, engine):
    guild, _, _, caller, fs, _, _ = launch(native=True, engine=engine)
    guild_id = guild.id
    harness.write(fs, "reference.pdf", harness.text_pdf("Harbor project budget is CAD 42000."))
    harness.write(fs, "blank.pdf", harness.text_pdf())
    payload = harness.file_request("Illustrate Harbor budget", ("reference.pdf", "blank.pdf"))
    for part in payload["messages"][0]["content"][:-1]:
        part["file_url"]["mime_type"] = "application/pdf"
    for _ in range(2):
        harness.send(caller, payload)
        result = harness.result(caller, 120)
        assert result.process_status == "completed", result.payload
        assert "Stored 2, searchable 1" in result.payload["description"]
    documents = [
        m for m in harness.instance(guild, "trace_probe").get_messages() if m.format.endswith("DocumentWorkflowResult")
    ]
    assert all(s["outcome"]["was_deduplicated"] for s in documents[-1].payload["sources"])
    assert [s["outcome"]["searchable"] for s in documents[-1].payload["sources"]] == [True, False]
    guild.shutdown()
    guild, _, _, caller, _, _, _ = launch(native=True, engine=engine, guild_id=guild_id)
    harness.send(caller, payload)
    assert harness.result(caller, 120).process_status == "completed"
    documents = [
        m for m in harness.instance(guild, "trace_probe").get_messages() if m.format.endswith("DocumentWorkflowResult")
    ]
    assert [s["outcome"]["searchable"] for s in documents[-1].payload["sources"]] == [True, False]


def test_identical_uploads_publish_independent_staging_files(launch, monkeypatch):
    _, coordinator, _, _, fs, _, _ = launch()
    data = b"Harbor project budget is CAD 42000."

    class Reader(HttpUploadSourceReader):
        async def read(self, url, max_bytes, deadline):
            return AcquiredUpload(data, "reference.md", "text/markdown")

    reader = Reader([])
    raw = {"file_url": {"url": "https://uploads.example.org/reference.md", "source_id": "reference:harbor"}}
    opened, resume = threading.Event(), threading.Event()
    original = fs.open

    class HeldWriter:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.stream.close()

        def write(self, value):
            opened.set()
            assert resume.wait(5)
            return self.stream.write(value)

    async def run():
        first, _ = await coordinator._source(raw, fs, reader, 1000, time.monotonic() + 10)

        def intercepted(path, mode="rb", **kwargs):
            stream = original(path, mode, **kwargs)
            return HeldWriter(stream) if mode == "wb" else stream

        monkeypatch.setattr(fs, "open", intercepted)
        second_task = asyncio.create_task(coordinator._source(raw, fs, reader, 1000, time.monotonic() + 10))
        try:
            assert await asyncio.to_thread(opened.wait, 5)
            assert await read_source_bytes(first, fs, 1000) == data
        finally:
            resume.set()
        second, _ = await second_task
        assert first.media_link.url != second.media_link.url
        assert first.source_id == second.source_id == "reference:harbor"

    asyncio.run(run())


@pytest.mark.parametrize("engine", harness.ENGINES)
@pytest.mark.parametrize("stage", ["ingest", "planner", "visualizer"])
@pytest.mark.parametrize("pause_at", ["context", "publish"])
def test_timeout_cancels_preparation_and_queued_dispatch(launch, monkeypatch, pause_at, stage, engine):
    _, coordinator, memory, caller, fs, llms, renderer = launch(deadline_seconds=0.5, engine=engine)
    entered, resume = threading.Event(), threading.Event()
    if pause_at == "context":
        original = coordinator._make_process_context

        def intercept(message, method, *args, **kwargs):
            if any(s.stage == stage for s in coordinator._requests.values()):
                entered.set()
                assert resume.wait(5)
            return original(message, method, *args, **kwargs)

        monkeypatch.setattr(coordinator, "_make_process_context", intercept)
    else:
        original = coordinator._client.publish

        def intercept_publish(message):
            if (message.session_state or {}).get(
                "paperbanana_stage"
            ) == stage and message.sender.id == coordinator.get_agent_tag().id:
                entered.set()
                assert resume.wait(5)
            return original(message)

        monkeypatch.setattr(coordinator._client, "publish", intercept_publish)
    if stage == "ingest":
        harness.write(fs, "reference.md")
        payload = harness.file_request("Draw Harbor")
    else:
        payload = {"messages": [{"role": "user", "content": "Draw Harbor"}]}
    worker = threading.Thread(target=harness.send, args=(caller, payload))
    worker.start()
    try:
        assert entered.wait(5)
        terminal = harness.result(caller, 3)
        assert terminal.process_status == "error" and "Workflow timed out" in terminal.payload["text"]
        resume.set()
        worker.join(5)
        assert not worker.is_alive()
        time.sleep(0.05)
        expected = 1 if stage == "visualizer" else 0
        assert len(llms["planner_agent"].calls) == len(llms["stylist_agent"].calls) == expected
        assert not llms["critic_agent"].calls and not renderer.calls
        if stage == "ingest":
            assert not memory.ingestions
        assert not coordinator._requests and not caller.get_messages()
    finally:
        resume.set()
        worker.join(5)


def test_early_source_timeout_continues_with_usable_sibling(launch, monkeypatch):
    guild, coordinator, _, caller, fs, _, _ = launch()
    reader = coordinator._dependency_resolvers["upload_reader"].reader

    async def timeout(*args, **kwargs):
        raise TimeoutError("Source backend timeout")

    monkeypatch.setattr(reader, "read", timeout)
    harness.write(fs, "good.md")
    harness.send(caller, harness.file_request("Draw Harbor", ("https://uploads.example.org/slow.md", "good.md")))
    assert harness.result(caller).process_status == "completed"
    terminal = [
        m for m in harness.instance(guild, "trace_probe").get_messages() if m.format.endswith("PaperBananaResult")
    ][-1]
    assert terminal.payload["sources"][0]["status"] == "failed"
    assert terminal.payload["sources"][0]["error"] == "source_acquisition_timed_out"
    assert terminal.payload["sources"][1]["outcome"]["searchable"]


def test_history_exclusion_and_control_fields_survive_context_budget(launch):
    historical = json.dumps({"payload": {"file_data": "data:text/plain;base64,cHJpdmF0ZQ=="}})
    context = {"enriched_history": [historical], **{f"metadata_{i}": "x" * 4000 for i in range(8)}}
    compact = compact_document_context({"paperbanana_deadline_ms": 42, "paperbanana_request_id": "request", **context})
    assert "enriched_history" not in compact and compact["paperbanana_deadline_ms"] == 42
    _, _, memory, caller, fs, _, _ = launch()
    harness.write(fs, "reference.md")
    harness.send(caller, harness.file_request("Draw Harbor"), session_state=context)
    assert harness.result(caller).process_status == "completed"
    assert "enriched_history" not in memory.ingestions[0].get_context()
    assert "enriched_history" not in memory.recalls[0].get_context()
    assert "private" not in str(memory.recalls[0].get_context())


def test_expiry_remains_independent_of_an_already_running_provider(launch, monkeypatch):
    _, coordinator, _, caller, _, llms, renderer = launch(deadline_seconds=0.5)
    entered, resume = threading.Event(), threading.Event()
    original = llms["planner_agent"].completion

    def completion(*args, **kwargs):
        entered.set()
        assert resume.wait(5)
        return original(*args, **kwargs)

    monkeypatch.setattr(llms["planner_agent"], "completion", completion)
    worker = threading.Thread(
        target=harness.send, args=(caller, {"messages": [{"role": "user", "content": "Draw Harbor"}]})
    )
    worker.start()
    try:
        assert entered.wait(5)
        terminal = harness.result(caller, 3)
        assert terminal.process_status == "error" and "Workflow timed out" in terminal.payload["text"]
        assert not coordinator._requests and worker.is_alive()
        resume.set()
        worker.join(5)
        assert not llms["stylist_agent"].calls and not renderer.calls and not caller.get_messages()
    finally:
        resume.set()
        worker.join(5)
