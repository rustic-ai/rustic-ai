"""Research Guild contracts and correlated orchestration regression tests."""

from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from rustic_ai.core.agents.commons.media import MediaLink
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
)
from rustic_ai.core.guild.dsl import GuildSpec
from rustic_ai.core.utils.basic_class_utils import get_class_from_name
from rustic_ai.playwright.agent import WebScrapingCompleted
from rustic_ai.serpapi.agent import SearchError, SERPResults
from rustic_ai.showcase.uniko_research import UnikoResearchCoordinator
from rustic_ai.uniko_agent import (
    FinalizeMemorySessionResult,
    IngestOutcome,
    MemoryAgentError,
    MemoryRecordKind,
    RecallItem,
    RecallResponse,
    RecordMemoryResult,
)


@pytest.fixture
def spec():
    return GuildSpec.model_validate(
        json.loads((Path(__file__).parent.parent / "apps/uniko_research_guild.json").read_text())["spec"]
    )


class Context:
    def __init__(self, payload, sender="upa-alice", identity=42, values=None):
        self.payload = payload
        self.message = SimpleNamespace(sender=SimpleNamespace(id=sender), id=identity, forward_header=None)
        self.values = deepcopy(values or {})
        self.sent = []

    def get_context(self):
        return deepcopy(self.values)

    def update_context(self, updates):
        self.values.update(updates)

    def send(self, payload):
        # Every routed payload must retain a valid serialized public contract.
        payload.__class__.model_validate(payload.model_dump(mode="json"))
        self.sent.append((payload, deepcopy(self.values)))

    def send_error(self, payload):
        self.send(payload)


def coordinator():
    value = UnikoResearchCoordinator.__new__(UnikoResearchCoordinator)
    value.guild_spec = SimpleNamespace(id="research-guild")
    return value


def respond(coord, emission, sender, payload, method):
    ctx = Context(payload, sender, values=emission[1])
    getattr(UnikoResearchCoordinator, method).__wfn__(coord, ctx)
    return ctx


def answer(text="Evidence-based answer"):
    return ChatCompletionResponse(
        id="response",
        created=1,
        model="test",
        choices=[{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
    )


def bundle(good=True):
    return RecallResponse(
        items=(
            [
                RecallItem(
                    node_id=1,
                    kind="chunk",
                    record_kind=MemoryRecordKind.EXTERNAL_EVIDENCE,
                    score=0.8,
                    content="Harbor budget 42000",
                    sources=[{"artifact_id": "artifact-1", "session_id": "owner"}],
                    source_id="source-1",
                    category="external_evidence",
                    token_count=6,
                )
            ]
            if good
            else []
        ),
        total_tokens=6 if good else 0,
        phase1_only=False,
        phase2_only=True,
        coverage=0.9 if good else 0,
    )


def record_ack(emission):
    req = emission[0]
    return RecordMemoryResult(record_id=req.record_id, session_id=req.session_id, kind=req.kind)


def finish(coord, synthesis):
    llm = respond(coord, synthesis, "synthesis_agent", answer(), "llm_result")
    assert llm.sent[0][1]["research_stage"] == "assistant_record"
    recorded = respond(coord, llm.sent[0], "memory_agent", record_ack(llm.sent[0]), "recorded")
    final = respond(
        coord,
        recorded.sent[0],
        "memory_agent",
        FinalizeMemorySessionResult(session_id=recorded.sent[0][0].session_id, rebuilt=True),
        "finalized",
    )
    return final


def test_blueprint_resolves_all_payloads_and_completion_points(spec):
    assert spec.dependency_map == {}
    assert len(spec.agents) == 8
    for step in spec.routes.steps:
        get_class_from_name(step.message_format)
        if step.agent:
            assert step.agent.id in {agent.id for agent in spec.agents}
        if step.process_status == "completed":
            assert step.agent.id == "research_coordinator"
            assert step.destination.topics in {"user_message_broadcast", "gateway_agent"}
    memory = next(a for a in spec.agents if a.id == "memory_agent")
    assert not memory.listen_to_default_topic
    assert memory.properties.scope_producers == ["research_coordinator"]
    synth = next(a for a in spec.agents if a.id == "synthesis_agent")
    assert synth.properties.max_tokens == 800
    assert not hasattr(memory.properties, "llm")
    assert "AnswerRequest" not in json.dumps(spec.model_dump(mode="json"))


def test_good_recall_passes_exact_context_and_finalizes_once():
    coord = coordinator()
    start = Context(ChatCompletionRequest(messages=[{"role": "user", "content": "What is the Harbor budget?"}]))
    UnikoResearchCoordinator.begin.__wfn__(coord, start)
    recalled = respond(coord, start.sent[0], "memory_agent", bundle(), "recalled")
    recorded = respond(coord, recalled.sent[0], "memory_agent", record_ack(recalled.sent[0]), "recorded")
    synthesis = recorded.sent[0]
    assert synthesis[1]["next_topic"] == "synthesis_agent"
    assert bundle().model_dump_json() in synthesis[0].messages[0].content
    assert "What is the Harbor budget?" in synthesis[0].messages[0].content
    final = finish(coord, synthesis)
    assert len(final.sent) == 1 and final.sent[0][1]["terminal"]
    late = respond(coord, synthesis, "synthesis_agent", answer("late answer"), "llm_result")
    assert not late.sent and not coord._requests
    duplicate = Context(start.payload)
    UnikoResearchCoordinator.begin.__wfn__(coord, duplicate)
    assert not duplicate.sent
    # A new request reuses the user's session; another user is isolated.
    follow = Context(start.payload, identity=43)
    UnikoResearchCoordinator.begin.__wfn__(coord, follow)
    other = Context(start.payload, sender="upa-bob", identity=44)
    UnikoResearchCoordinator.begin.__wfn__(coord, other)
    assert follow.sent[0][0].scope.sessions == start.sent[0][0].scope.sessions
    assert other.sent[0][0].scope.sessions != start.sent[0][0].scope.sessions


def test_document_barrier_partial_failure_and_late_results():
    coord = coordinator()
    files = [
        MediaLink(url="uploads/one.txt", name="one.txt", on_filesystem=True),
        MediaLink(url="uploads/two.txt", name="two.txt", on_filesystem=True),
    ]
    start = Context(ChatCompletionRequest(messages=[{"role": "user", "content": "Summarize files"}]))
    coord._begin(start, "Summarize files", files)
    recorded = respond(coord, start.sent[0], "memory_agent", record_ack(start.sent[0]), "recorded")
    assert len(recorded.sent) == 2
    good = respond(
        coord,
        recorded.sent[0],
        "memory_agent",
        IngestOutcome(stored=True, searchable=True, success=True, record_id=recorded.sent[0][0].record_id),
        "ingested",
    )
    assert not good.sent
    duplicate = respond(coord, recorded.sent[0], "memory_agent", IngestOutcome(success=True), "ingested")
    assert not duplicate.sent
    failed = respond(
        coord,
        recorded.sent[1],
        "memory_agent",
        MemoryAgentError(error="document_ingest_failed", message="failed"),
        "memory_failed",
    )
    assert len(failed.sent) == 1 and failed.sent[0][1]["research_stage"] == "post_research"
    assert MemoryRecordKind.USER_ASSERTION not in failed.sent[0][0].allowed_record_kinds
    synthesis = respond(coord, failed.sent[0], "memory_agent", bundle(), "recalled")
    final = finish(coord, synthesis.sent[0])
    assert len(final.sent) == 1
    late = respond(coord, recorded.sent[1], "memory_agent", IngestOutcome(stored=True, searchable=True), "ingested")
    assert not late.sent


def test_search_enumeration_and_terminal_failure():
    coord = coordinator()
    start = Context(ChatCompletionRequest(messages=[{"role": "user", "content": "Research an obscure topic"}]))
    UnikoResearchCoordinator.begin.__wfn__(coord, start)
    recalled = respond(coord, start.sent[0], "memory_agent", bundle(False), "recalled")
    recorded = respond(coord, recalled.sent[0], "memory_agent", record_ack(recalled.sent[0]), "recorded")
    generated = respond(coord, recorded.sent[0], "query_agent", answer("first####second"), "llm_result")
    assert len(generated.sent) == 4
    google = [e for e in generated.sent if e[1]["next_topic"] == "google_agent"]
    search = [e for e in generated.sent if e[1]["next_topic"] == "serp_agent"]
    for emission in google:
        failed = respond(
            coord,
            emission,
            "google_agent",
            MemoryAgentError(error="provider_failed", message="failed"),
            "memory_failed",
        )
        assert not failed.sent
    one = respond(
        coord,
        search[0],
        "serp_agent",
        SERPResults(
            engine="google",
            query="first",
            count=1,
            id=search[0][0].id,
            results=[MediaLink(url="https://example.com", name="example")],
        ),
        "searched",
    )
    assert one.sent[0][1]["next_topic"] == "playwright_agent"
    no_search = respond(coord, search[1], "serp_agent", SearchError(id=search[1][0].id, response={}), "search_failed")
    assert not no_search.sent
    completed = respond(
        coord, one.sent[0], "playwright_agent", WebScrapingCompleted(id=one.sent[0][0].id, links=[]), "scraped"
    )
    assert completed.sent[0][1]["research_stage"] == "post_research"
    final = respond(coord, completed.sent[0], "memory_agent", bundle(False), "recalled")
    assert len(final.sent) == 1 and final.sent[0][1]["terminal"]
    assert "No relevant evidence" in final.sent[0][0].choices[0].message.content


def test_untrusted_result_cannot_advance_barrier():
    coord = coordinator()
    start = Context(ChatCompletionRequest(messages=[{"role": "user", "content": "Question"}]))
    UnikoResearchCoordinator.begin.__wfn__(coord, start)
    attacker = respond(coord, start.sent[0], "upa-mallory", bundle(), "recalled")
    assert not attacker.sent
    assert len(coord._requests) == 1


def test_dispatch_releases_request_lock_before_sync_callbacks(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    coord = coordinator()
    ctx = Context(ChatCompletionRequest(messages=[{"role": "user", "content": "Question"}]))
    original_send = ctx.send

    def send(payload):
        def acquire_on_other_thread():
            lock = coord._storage()
            acquired = lock.acquire(timeout=0.1)
            if acquired:
                lock.release()
            return acquired

        with ThreadPoolExecutor(max_workers=1) as executor:
            assert executor.submit(acquire_on_other_thread).result(timeout=2)
        original_send(payload)

    monkeypatch.setattr(ctx, "send", send)
    UnikoResearchCoordinator.begin.__wfn__(coord, ctx)
    assert len(ctx.sent) == 1


@pytest.mark.asyncio
async def test_sequential_research_rounds_with_native_memory():
    """Real memory across document ingestion, follow-up and another user's request."""
    from collections import deque

    import fsspec
    from uniko import Uniko

    from rustic_ai.uniko_agent import (
        FinalizeMemorySessionRequest,
        IngestDocumentRequest,
        MemoryAgent,
        MemoryAgentConfig,
        RecallRequest,
        RecordMemoryRequest,
    )

    coord = coordinator()
    native = Uniko.builder().in_memory().build_sync()
    handles = [native.agent("research-memory")]
    mem = MemoryAgent.__new__(MemoryAgent)
    mem.config = MemoryAgentConfig(scope_producers=["research_coordinator"])
    mem.guild_spec = coord.guild_spec
    fs = fsspec.filesystem("memory")
    fs.pipe("g1/research-harbor.txt", b"Harbor Project approved budget is CAD 42000. Coordinator is Mina Patel.")
    document = MediaLink(url="g1/research-harbor.txt", name="harbor.txt", on_filesystem=True, mimetype="text/plain")
    memory_requests = {
        RecallRequest: "recall_knowledge",
        RecordMemoryRequest: "record_memory",
        IngestDocumentRequest: "ingest_document",
        FinalizeMemorySessionRequest: "finalize_memory_session",
    }
    memory_responses = {
        RecallResponse: "recalled",
        RecordMemoryResult: "recorded",
        IngestOutcome: "ingested",
        FinalizeMemorySessionResult: "finalized",
        MemoryAgentError: "memory_failed",
    }

    async def run(user, identity, files):
        start = Context(
            ChatCompletionRequest(
                messages=[{"role": "user", "content": "What is the Harbor Project approved budget?"}]
            ),
            sender=user,
            identity=identity,
        )
        coord._begin(start, start.payload.messages[0].content, files)
        queue = deque((payload, values, "research_coordinator") for payload, values in start.sent)
        final = []
        bundles = []
        for _ in range(100):
            if not queue:
                break
            payload, values, sender = queue.popleft()
            if values.get("terminal"):
                final.append(payload)
                continue
            ctx = Context(payload, sender=sender, identity=identity, values=values)
            if type(payload) in memory_requests:
                method = getattr(MemoryAgent, memory_requests[type(payload)]).__wfn__
                if isinstance(payload, IngestDocumentRequest):
                    await method(mem, ctx, handles[0], None, fs)
                else:
                    await method(mem, ctx, handles[0])
                output_sender = "memory_agent"
            elif type(payload) in memory_responses:
                if isinstance(payload, RecallResponse):
                    bundles.append(payload)
                getattr(UnikoResearchCoordinator, memory_responses[type(payload)]).__wfn__(coord, ctx)
                output_sender = "research_coordinator"
            elif isinstance(payload, ChatCompletionResponse):
                UnikoResearchCoordinator.llm_result.__wfn__(coord, ctx)
                output_sender = "research_coordinator"
            elif isinstance(payload, ChatCompletionRequest):
                if values["next_topic"] == "synthesis_agent":
                    assert bundles[-1].model_dump_json() in payload.messages[0].content
                    ctx.send(answer("Harbor Project approved budget is CAD 42000."))
                    output_sender = "synthesis_agent"
                else:
                    ctx.send(answer("Harbor approved budget"))
                    output_sender = "query_agent"
            else:
                assert values["next_topic"] in {"google_agent", "serp_agent"}
                output_sender = values["next_topic"]
                if output_sender == "google_agent":
                    ctx.send(MemoryAgentError(error="provider_failed", message="Unavailable in controlled test"))
                else:
                    error = SearchError(id=payload.id, response={})
                    error_ctx = Context(error, sender="serp_agent", values=values)
                    UnikoResearchCoordinator.search_failed.__wfn__(coord, error_ctx)
                    ctx.sent.extend(error_ctx.sent)
                    output_sender = "research_coordinator"
            queue.extend((item, state, output_sender) for item, state in ctx.sent)
        assert not queue
        assert len(final) == 1
        assert not coord._requests
        return final[0]

    first = await run("upa-alice", 100, [document])
    assert "CAD 42000" in first.choices[0].message.content
    follow = await run("upa-alice", 101, [])
    assert "CAD 42000" in follow.choices[0].message.content
    other = await run("upa-bob", 102, [])
    assert "No relevant evidence" in other.choices[0].message.content
    handles.clear()
    await native.shutdown()
