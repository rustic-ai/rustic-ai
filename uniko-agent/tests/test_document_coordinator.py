"""Real-bus workflow tests plus immutable-source and native persistence checks."""

import base64
import importlib.util
import json
from pathlib import Path
import time
from uuid import uuid4

from fsspec.implementations.memory import MemoryFileSystem
from pydantic import ValidationError
import pytest

from rustic_ai.core.agents.commons.media import MediaLink
from rustic_ai.core.agents.testutils import ProbeAgent
from rustic_ai.core.guild.agent import Agent, ProcessContext, ProcessorHelper, processor
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder, RouteBuilder
from rustic_ai.core.guild.dsl import DependencySpec
from rustic_ai.core.messaging.core.message import ProcessStatus
from rustic_ai.uniko_agent import (
    DocumentCoordinatorAgent,
    DocumentCoordinatorConfig,
    DocumentWorkflowError,
    DocumentWorkflowRequest,
    DocumentWorkflowResult,
    IngestDocumentRequest,
    IngestOutcome,
    MemoryAgent,
    MemoryAgentConfig,
    MemoryAgentError,
    MemorySource,
    RecallItem,
    RecallRequest,
    RecallResponse,
    normalize_document_attachment,
)
from rustic_ai.uniko_agent.document_sources import snapshot_document

ENGINES = ["sync.sync_exec_engine.SyncExecutionEngine", "multithreaded.multithreaded_exec_engine.MultiThreadedEngine"]


class ControlledMemory(Agent):
    def __init__(self):
        self.ingestions = []
        self.recalls = []

    @processor(IngestDocumentRequest)
    def ingest(self, ctx: ProcessContext[IngestDocumentRequest]):
        self.ingestions.append(ctx)
        text = base64.b64decode(ctx.payload.source.base64_data).decode()
        if "hold" in text:
            return
        if "fail" in text:
            ctx.send_error(MemoryAgentError(error="document_ingest_failed", message="Rejected"))
        else:
            ctx.send(
                IngestOutcome(
                    record_id=ctx.payload.record_id,
                    stored=True,
                    searchable="archive" not in text,
                    chunk_count=0 if "archive" in text else 1,
                )
            )

    @processor(RecallRequest)
    def recall(self, ctx: ProcessContext[RecallRequest]):
        self.recalls.append(ctx)
        if ctx.payload.query == "hold":
            return
        if ctx.payload.query == "error":
            ctx.send_error(MemoryAgentError(error="recall_failed", message="Recall failed"))
            return
        items = (
            []
            if ctx.payload.query == "empty"
            else [
                RecallItem(
                    node_id=1,
                    kind="Chunk",
                    sources=[],
                    content="Harbor evidence " * 100,
                    score=0.9,
                    token_count=300,
                    record_kind="external_evidence",
                    source_ids=["harbor"],
                )
            ]
        )
        ctx.send(
            RecallResponse(
                items=items, total_tokens=300 if items else 0, phase1_only=False, phase2_only=False, coverage=1.0
            )
        )


def instance(guild, agent_id):
    wrapper = guild.execution_engine.agent_tracker.get_agent_wrapper(guild.id, agent_id)
    if hasattr(wrapper, "initialization_complete"):
        assert wrapper.initialization_complete.wait(5)
    assert wrapper.agent is not None
    return wrapper.agent


def wait_for(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(0.01)
    raise AssertionError("Expected workflow event did not arrive")


@pytest.fixture
def launch(tmp_path):
    guilds = []

    def build(engine=ENGINES[0], native=False, guild_id=None, **overrides):
        coordinator = (
            AgentBuilder(DocumentCoordinatorAgent)
            .set_id("documents")
            .set_name("Documents")
            .set_description("Document workflow")
            .set_properties(
                DocumentCoordinatorConfig(corpus_session_id="corpus:references", memory_agent_id="memory", **overrides)
            )
            .listen_to_default_topic(False)
            .add_additional_topic("requests")
            .add_additional_topic("memory.results")
            .build_spec()
        )
        memory_builder = (
            AgentBuilder(MemoryAgent if native else ControlledMemory)
            .set_id("memory")
            .set_name("Memory")
            .set_description("Corpus")
            .listen_to_default_topic(False)
            .add_additional_topic("commands")
        )
        if native:
            memory_builder.set_properties(
                MemoryAgentConfig(
                    scope_producers=["documents"], allowed_record_producers={"external_evidence": ["documents"]}
                )
            )
        memory = memory_builder.build_spec()
        caller = (
            AgentBuilder(ProbeAgent)
            .set_id("caller")
            .set_name("Caller")
            .set_description("Caller")
            .listen_to_default_topic(False)
            .add_additional_topic("results")
            .build_spec()
        )
        builder = GuildBuilder(guild_id or "documents-" + uuid4().hex, "Documents", "Workflow tests")
        builder.set_execution_engine("rustic_ai.core.guild.execution." + engine)
        builder.set_dependency_map(
            {
                "filesystem": DependencySpec(
                    class_name="rustic_ai.core.guild.agent_ext.depends.filesystem.FileSystemResolver",
                    properties={
                        "protocol": "file",
                        "path_base": str(tmp_path),
                        "storage_options": {"auto_mkdir": True},
                    },
                ),
                "uniko": DependencySpec(
                    class_name="rustic_ai.uniko_agent.UnikoResolver",
                    properties={"storage_path": "corpus.db", "streaming": False},
                ),
            }
        )
        for spec in (coordinator, memory, caller):
            builder.add_agent_spec(spec)
        for sender, formats, topic, status in (
            (coordinator, (IngestDocumentRequest, RecallRequest), "commands", ProcessStatus.RUNNING),
            (memory, (IngestOutcome, RecallResponse, MemoryAgentError), "memory.results", ProcessStatus.RUNNING),
            (coordinator, (DocumentWorkflowResult,), "results", ProcessStatus.COMPLETED),
            (coordinator, (DocumentWorkflowError,), "results", ProcessStatus.ERROR),
        ):
            for model in formats:
                builder.add_route(
                    RouteBuilder(sender)
                    .on_message_format(model)
                    .set_destination_topics(topic)
                    .set_process_status(status)
                    .set_route_times(-1)
                    .build()
                )
        guild = builder.launch("document-tests")
        guilds.append(guild)
        return guild, instance(guild, "documents"), instance(guild, "memory"), instance(guild, "caller")

    yield build
    for guild in guilds:
        guild.shutdown()


def send(caller, request):
    caller.publish_with_guild_route("requests", request)


def terminal(caller, timeout=5):
    messages = wait_for(caller.get_messages, timeout)
    assert len(messages) == 1
    message = messages[0]
    caller.clear_messages()
    model = DocumentWorkflowError if message.is_error_message else DocumentWorkflowResult
    expected = ProcessStatus.ERROR if message.is_error_message else ProcessStatus.COMPLETED
    assert message.process_status == expected
    return model.model_validate(message.payload)


@pytest.mark.parametrize("engine", ENGINES)
def test_barrier_duplicate_late_and_bounded_recall(launch, engine):
    guild, coordinator, memory, caller = launch(engine=engine, recall_max_characters=50, recall_token_budget=20)
    request = DocumentWorkflowRequest(
        request_id="barrier",
        sources=[MemorySource(text="hold one", source_id="one"), MemorySource(text="hold two", source_id="two")],
        query="budget",
    )
    send(caller, request)
    wait_for(lambda: len(memory.ingestions) == 2)
    send(caller, request)
    assert len(memory.ingestions) == 2
    second, first = memory.ingestions[1], memory.ingestions[0]
    outcome = IngestOutcome(record_id=second.payload.record_id, stored=True, searchable=True)
    second.send(outcome)
    second.send(outcome)
    second.send_error(MemoryAgentError(error="late_error", message="Late"))
    assert not memory.recalls
    assert not caller.get_messages()
    first.send(IngestOutcome(record_id=first.payload.record_id, stored=True, searchable=True))
    result = terminal(caller)
    assert isinstance(result, DocumentWorkflowResult)
    assert len(result.sources) == 2
    assert result.recall.truncated
    assert sum(len(x.content) + len(x.context or "") for x in result.recall.items) <= 50
    assert result.recall.total_tokens <= 20
    assert memory.recalls[0].payload.scope.sessions == ["corpus:references"]
    assert memory.recalls[0].payload.allowed_record_kinds == ["external_evidence"]
    second.send_error(MemoryAgentError(error="late_error", message="Late"))
    send(caller, request)
    assert not caller.get_messages()
    assert not coordinator._workflows
    assert not coordinator._scheduled_jobs
    guild.shutdown()
    assert coordinator._scheduler is None


@pytest.mark.parametrize(
    "sources,query,partial,required,error",
    [
        (["ok"], None, False, True, None),
        (["archive"], None, False, True, None),
        (["ok", "fail"], "budget", True, True, None),
        (["ok", "fail"], "budget", False, True, "document_ingestion_failed"),
        (["fail"], None, True, True, "document_ingestion_failed"),
        (["archive"], "empty", False, True, "document_evidence_unavailable"),
        ([], "empty", False, False, None),
        ([], "empty", False, True, "document_evidence_unavailable"),
        ([], "error", False, True, "document_recall_failed"),
    ],
)
def test_outcomes_and_failure_paths(launch, sources, query, partial, required, error):
    _, coordinator, _, caller = launch()
    send(
        caller,
        DocumentWorkflowRequest(
            request_id="outcome",
            sources=[MemorySource(text=x) for x in sources],
            query=query,
            allow_partial=partial,
            require_evidence=required,
        ),
    )
    result = terminal(caller)
    if error:
        assert isinstance(result, DocumentWorkflowError)
        assert result.error == error
    else:
        assert isinstance(result, DocumentWorkflowResult)
        if "archive" in sources:
            assert result.sources[0].outcome.stored
            assert not result.sources[0].outcome.searchable
        assert result.partial == ("fail" in sources)
    assert not coordinator._workflows


def test_timeout_unknown_late_results_and_capacity(launch):
    _, coordinator, memory, caller = launch(deadline_seconds=0.2, max_active_workflows=1)
    request = DocumentWorkflowRequest(request_id="slow", sources=[MemorySource(text="hold")])
    send(caller, request)
    wait_for(lambda: memory.ingestions)
    send(caller, DocumentWorkflowRequest(request_id="busy", query="budget"))
    capacity = terminal(caller)
    assert capacity.error == "document_capacity_exceeded"
    result = terminal(caller)
    assert result.error == "document_workflow_timed_out"
    assert result.sources[0].status == "unknown"
    ctx = memory.ingestions[0]
    ctx.send(IngestOutcome(record_id=ctx.payload.record_id, stored=True, searchable=True))
    ctx.send_error(MemoryAgentError(error="late", message="Late"))
    assert not caller.get_messages()
    assert not coordinator._workflows


def test_identity_conflict_untrusted_reply_and_old_attempt(launch):
    _, coordinator, memory, caller = launch()
    request = DocumentWorkflowRequest(request_id="conflict", sources=[MemorySource(text="hold")])
    send(caller, request)
    wait_for(lambda: memory.ingestions)
    ctx = memory.ingestions[0]
    caller.publish_dict(
        "memory.results",
        IngestOutcome(record_id=ctx.payload.record_id, stored=True),
        format=IngestOutcome,
        session_state=ctx.get_context(),
    )
    assert not caller.get_messages()
    context = ctx.get_context()
    context["document_attempt_id"] = "previous-attempt"
    forged = ProcessContext(
        memory, ctx.message.model_copy(update={"session_state": context}), "ingest", IngestDocumentRequest
    )
    forged.send(IngestOutcome(record_id=ctx.payload.record_id, stored=True))
    assert not caller.get_messages()
    send(caller, DocumentWorkflowRequest(request_id="conflict", query="different"))
    assert terminal(caller).error == "request_id_conflict"
    assert not coordinator._workflows


def test_limits_deduplication_and_tombstone_bound(launch):
    _, coordinator, memory, caller = launch(max_source_bytes=4, max_workflow_bytes=6, completed_request_limit=2)
    send(caller, DocumentWorkflowRequest(request_id="large", sources=[MemorySource(text="12345")]))
    assert terminal(caller).sources[0].error == "document_source_rejected"
    assert not memory.ingestions
    send(
        caller,
        DocumentWorkflowRequest(request_id="total", sources=[MemorySource(text="1234"), MemorySource(text="abcd")]),
    )
    assert terminal(caller).error == "document_ingestion_failed"
    send(
        caller,
        DocumentWorkflowRequest(request_id="duplicates", sources=[MemorySource(text="ok"), MemorySource(text="ok")]),
    )
    result = terminal(caller)
    assert result.sources[0].record_id == result.sources[1].record_id
    assert len(memory.ingestions) == 2  # one previous source, one unique current source
    assert len(coordinator._completed) == 2


@pytest.mark.asyncio
async def test_metadata_immutable_snapshots_and_revisions():
    fs = MemoryFileSystem()
    fs.pipe("/snapshot.txt", b"first")
    source = MemorySource(
        media_link=MediaLink(
            url="/snapshot.txt",
            name="plan.md",
            mimetype="text/markdown",
            on_filesystem=True,
            metadata={"source_uri": "https://example.test/plan"},
        )
    )
    first, first_outcome, _ = await snapshot_document(source, "corpus", fs, 100, 0)
    fs.pipe("/snapshot.txt", b"second")
    _, second_outcome, _ = await snapshot_document(source, "corpus", fs, 100, 0)
    _, repeated, _ = await snapshot_document(source, "corpus", fs, 100, 0)
    assert base64.b64decode(first.base64_data) == b"first"
    assert first_outcome.source_id == second_outcome.source_id
    assert first_outcome.revision_id != second_outcome.revision_id
    assert second_outcome.record_id == repeated.record_id
    assert first_outcome.name == "plan.md"
    assert first_outcome.mime_type == "text/markdown"
    assert first_outcome.source_uri == "https://example.test/plan"
    _, other, _ = await snapshot_document(source, "another-corpus", fs, 100, 0)
    assert other.source_id != first_outcome.source_id


def test_raw_transport_normalization_and_validation():
    source = normalize_document_attachment(
        {
            "type": "file_url",
            "file_url": {
                "url": "file:///guild/plan.md",
                "filename": "Original.md",
                "mime_type": "text/markdown",
                "metadata": {"source_uri": "https://example.test/original"},
            },
        }
    )
    assert source.media_link.name == "Original.md"
    assert source.media_link.mimetype == "text/markdown"
    assert source.media_link.metadata["source_uri"] == "https://example.test/original"
    assert source.media_link.url == "/guild/plan.md"
    assert normalize_document_attachment({"mediaLink": source.media_link.model_dump()}).media_link.name == "Original.md"
    assert (
        normalize_document_attachment(
            {"type": "file", "file": {"filename": "Plan.md", "file_data": "data:text/markdown;base64,aGk="}}
        ).base64_data
        == "aGk="
    )
    assert (
        normalize_document_attachment({"mediaLink": None, "name": "Plan.md", "url": "file:///plan.md"}).media_link.name
        == "Plan.md"
    )
    assert (
        normalize_document_attachment(
            {"type": "file", "file": {"filename": "Plan.md", "file_data": "data:;base64,YQ=="}}
        ).mime_type
        is None
    )
    with pytest.raises(ValidationError):
        normalize_document_attachment({"url": "https://example.test/remote"})
    for data in (
        {"request_id": "empty"},
        {"request_id": "blank", "query": " "},
        {"request_id": "too-many", "sources": [{"text": "a"}] * 33},
    ):
        with pytest.raises(ValidationError):
            DocumentWorkflowRequest.model_validate(data)


@pytest.mark.parametrize("engine", ENGINES)
def test_native_ingestion_reopen_and_retry(launch, engine):
    guild_id = "persistent-" + uuid4().hex
    guild, _, memory, caller = launch(engine=engine, native=True, guild_id=guild_id)
    request = DocumentWorkflowRequest(
        request_id="first",
        sources=[
            MemorySource(
                text="Harbor pilot budget is CAD 42000. Mina Patel coordinates it.",
                source_id="harbor-plan",
                path_hint="plan.txt",
            )
        ],
        query="Harbor pilot budget coordinator",
    )
    send(caller, request)
    first = terminal(caller, 120)
    assert isinstance(first, DocumentWorkflowResult), first
    assert first.sources[0].outcome.stored and first.sources[0].outcome.searchable
    assert "42000" in " ".join(x.content for x in first.recall.items)
    resolver = memory._dependency_resolvers["uniko"]
    guild.shutdown()
    assert resolver._closing and not resolver._runtimes and not resolver._uniko_instances
    reopened, _, _, second_caller = launch(engine=engine, native=True, guild_id=guild_id)
    send(second_caller, request.model_copy(update={"request_id": "retry"}))
    second = terminal(second_caller, 120)
    assert isinstance(second, DocumentWorkflowResult), second
    assert second.sources[0].record_id == first.sources[0].record_id
    assert second.sources[0].outcome.was_deduplicated
    send(second_caller, DocumentWorkflowRequest(request_id="read", query="Harbor pilot budget"))
    assert terminal(second_caller, 120).recall.items
    other, _, _, other_caller = launch(engine=engine, native=True)
    send(other_caller, DocumentWorkflowRequest(request_id="isolated", query="Harbor pilot budget"))
    assert terminal(other_caller, 120).error == "document_evidence_unavailable"
    other.shutdown()
    reopened.shutdown()


def test_foundation_example_and_schemas(tmp_path):
    path = Path(__file__).parents[1] / "examples/document_guild.py"
    spec = importlib.util.spec_from_file_location("document_guild", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    guild_spec = module.build_document_guild(str(tmp_path)).build_spec()
    type(guild_spec).model_validate(guild_spec.model_dump(), context={"require_agent_class": True})
    schema_dir = Path(__file__).parents[1] / "src/rustic_ai/uniko_agent/schemas"
    for model, name in [
        (DocumentCoordinatorConfig, "document-coordinator-config"),
        (DocumentWorkflowRequest, "document-workflow-request"),
        (DocumentWorkflowResult, "document-workflow-result"),
        (DocumentWorkflowError, "document-workflow-error"),
    ]:
        assert json.loads((schema_dir / (name + ".schema.json")).read_text()) == model.model_json_schema()


def blank_pdf():
    """Small valid PDF fixture without adding a PDF-generation dependency."""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Resources << >> /Contents 4 0 R >>",
        b"<< /Length 0 >>\nstream\n\nendstream",
    ]
    data = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, value in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f"{index} 0 obj\n".encode() + value + b"\nendobj\n")
    xref = len(data)
    data.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode())
    data.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(data)


def test_native_filesystem_sources_and_unsearchable_pdf(launch):
    guild, _, memory, caller = launch(native=True)
    filesystem = memory._dependency_resolvers["filesystem"].get_or_resolve("document-tests", guild.id, None)
    with filesystem.open("harbor.md", "wb") as stream:
        stream.write(b"# Harbor\nHarbor document budget is CAD 42000; the project coordinator is Mina Patel.")
    with filesystem.open("blank.pdf", "wb") as stream:
        stream.write(blank_pdf())
    send(
        caller,
        DocumentWorkflowRequest(
            request_id="native-files",
            sources=[
                MemorySource(
                    media_link=MediaLink(
                        url="harbor.md",
                        name="Original.md",
                        mimetype="text/markdown",
                        metadata={"source_uri": "https://example.test/harbor"},
                        on_filesystem=True,
                    )
                ),
                MemorySource(
                    media_link=MediaLink(
                        url="blank.pdf", name="Blank.pdf", mimetype="application/pdf", on_filesystem=True
                    )
                ),
            ],
            query="Harbor project budget coordinator",
            allow_partial=True,
        ),
    )
    result = terminal(caller, 120)
    assert isinstance(result, DocumentWorkflowResult), result
    assert result.sources[0].name == "Original.md"
    assert result.sources[0].source_uri == "https://example.test/harbor"
    assert result.sources[0].outcome.searchable
    assert result.sources[1].outcome.stored
    assert not result.sources[1].outcome.searchable
    assert "42000" in " ".join(x.content for x in result.recall.items)


def test_malformed_request_uses_typed_error_without_side_effects(launch):
    _, _, memory, caller = launch()
    caller.publish_dict(
        "requests",
        {"request_id": "invalid", "sources": [{"text": "a", "base64_data": "Yg=="}]},
        format=DocumentWorkflowRequest,
        routing_slip=caller.guild_spec.routes,
    )
    result = terminal(caller)
    assert isinstance(result, DocumentWorkflowError)
    assert result.error == "document_request_invalid"
    assert not memory.ingestions


def test_recall_timeout_and_shutdown_with_pending_work(launch):
    guild, coordinator, memory, caller = launch(deadline_seconds=0.05)
    send(caller, DocumentWorkflowRequest(request_id="recall-timeout", query="hold"))
    wait_for(lambda: memory.recalls)
    assert terminal(caller).error == "document_workflow_timed_out"
    send(caller, DocumentWorkflowRequest(request_id="shutdown-pending", sources=[MemorySource(text="hold")]))
    wait_for(lambda: memory.ingestions)
    guild.shutdown()
    assert coordinator._closing and not coordinator._workflows
    assert coordinator._scheduler is None
    time.sleep(0.08)
    assert not caller.get_messages()


def test_duplicate_metadata_order_does_not_conflict(launch):
    guild, coordinator, memory, caller = launch()
    filesystem = coordinator._dependency_resolvers["filesystem"].get_or_resolve("document-tests", guild.id, None)
    with filesystem.open("ordering.md", "wb") as stream:
        stream.write(b"hold")
    first = MemorySource(
        media_link=MediaLink(url="ordering.md", on_filesystem=True, metadata={"first": 1, "second": 2})
    )
    request = DocumentWorkflowRequest(request_id="ordering", sources=[first])
    send(caller, request)
    wait_for(lambda: memory.ingestions)
    reordered = request.model_dump(mode="json")
    reordered["sources"][0]["media_link"]["metadata"] = {"second": 2, "first": 1}
    caller.publish_dict("requests", reordered, format=DocumentWorkflowRequest, routing_slip=caller.guild_spec.routes)
    assert not caller.get_messages()
    assert len(memory.ingestions) == 1
    assert "ordering" in coordinator._workflows


def test_rebased_context_preserves_send_error_and_modifier_fixtures(launch, monkeypatch):
    def sent(agent, ctx):
        assert ctx.payload["request_id"] in {"fixture-success", "fixture-error"}
        ctx.update_context({"send_fixture": True})

    def error(agent, ctx):
        ctx.update_context({"error_fixture": True})

    def modify(agent, ctx, message):
        message.session_state["modifier_fixture"] = True

    monkeypatch.setattr(
        ProcessorHelper, "get_on_send_fixtures", lambda cls: [sent] if cls is DocumentCoordinatorAgent else []
    )
    monkeypatch.setattr(
        ProcessorHelper, "get_on_error_fixtures", lambda cls: [error] if cls is DocumentCoordinatorAgent else []
    )
    monkeypatch.setattr(
        ProcessorHelper, "get_message_mod_fixtures", lambda cls: [modify] if cls is DocumentCoordinatorAgent else []
    )
    _, _, _, caller = launch()
    for request_id, text, marker in [
        ("fixture-success", "ok", "send_fixture"),
        ("fixture-error", "fail", "error_fixture"),
    ]:
        send(caller, DocumentWorkflowRequest(request_id=request_id, sources=[MemorySource(text=text)]))
        message = wait_for(caller.get_messages)[0]
        assert message.session_state[marker]
        assert message.session_state["modifier_fixture"]
        caller.clear_messages()
