"""Acceptance tests execute the shipped guild with native local stores."""

from copy import deepcopy
import json
from pathlib import Path
import time
from uuid import uuid4

import pytest

from rustic_ai.core.agents.commons.media import MediaLink
from rustic_ai.core.agents.testutils import ProbeAgent
from rustic_ai.core.agents.utils.user_proxy_agent import UserProxyAgent
from rustic_ai.core.guild.agent import Agent, ProcessContext, processor
from rustic_ai.core.guild.agent_ext.depends import DependencyResolver
from rustic_ai.core.guild.agent_ext.depends.llm.llm import LLM
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
)
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.guild.dsl import GuildSpec
from rustic_ai.core.messaging.core.message import Message
from rustic_ai.core.utils import Priority
from rustic_ai.core.utils.gemstone_id import GemstoneID
from rustic_ai.playwright.agent import WebScrapingCompleted, WebScrapingRequest

BLUEPRINT = Path(__file__).parents[1] / "apps/semantic_memory_assistant.json"
ENGINES = ["sync.sync_exec_engine.SyncExecutionEngine", "multithreaded.multithreaded_exec_engine.MultiThreadedEngine"]


def response(text="Accepted answer", tools=None, finish=None):
    return ChatCompletionResponse(
        id=uuid4().hex,
        created=1,
        model="local-test",
        choices=[
            {
                "index": 0,
                "message": {"role": "assistant", "content": text, "tool_calls": tools},
                "finish_reason": finish or ("tool_calls" if tools else "stop"),
            }
        ],
    )


def scrape_call(id="call-1", url="https://example.test/harbor", **args):
    return {
        "id": id,
        "type": "function",
        "function": {
            "name": "web_scrape",
            "arguments": json.dumps({"links": [{"url": url}], "output_format": "text/markdown", **args}),
        },
    }


class LocalLLM(LLM):
    def __init__(self):
        self.calls = []
        self.responses = []

    @property
    def model(self):
        return "local-test"

    def get_config(self):
        return {}

    def completion(self, prompt, model=None):
        self.calls.append(prompt)
        value = self.responses.pop(0) if self.responses else response()
        if isinstance(value, Exception):
            raise value
        if callable(value):
            return value(prompt)
        return value

    async def async_completion(self, prompt, model=None):
        return self.completion(prompt, model)


class LocalLLMResolver(DependencyResolver[LLM]):
    def resolve(self, org_id, guild_id, agent_id):
        return LocalLLM()


class Scraper(Agent):
    def __init__(self):
        self.calls = []
        self.failures = []
        self.hold = False

    @processor(WebScrapingRequest, depends_on=["filesystem:guild_fs:guild"])
    def scrape(self, ctx: ProcessContext[WebScrapingRequest], guild_fs):
        self.calls.append(ctx)
        if self.hold:
            return
        fail = self.failures.pop(0) if self.failures else False
        links = []
        if not fail:
            name = "harbor-" + uuid4().hex + ".md"
            with guild_fs.open(name, "wb") as stream:
                stream.write(b"Harbor project budget is CAD 42000. Mina Patel is coordinator.")
            links = [
                MediaLink(
                    url=name,
                    name=name,
                    mimetype="text/markdown",
                    on_filesystem=True,
                    metadata={"source_uri": ctx.payload.links[0].url},
                )
            ]
        ctx.send(WebScrapingCompleted(id=ctx.payload.id, links=links))


def instance(guild, id):
    wrapper = guild.execution_engine.agent_tracker.get_agent_wrapper(guild.id, id)
    if hasattr(wrapper, "initialization_complete"):
        assert wrapper.initialization_complete.wait(5)
    return wrapper.agent


def wait(predicate, timeout=120):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(0.01)
    raise AssertionError("Workflow event missing")


@pytest.fixture
def launch(tmp_path):
    guilds = []

    def build(engine=ENGINES[0], guild_id=None, real_scraper=False, **config):
        data = deepcopy(json.loads(BLUEPRINT.read_text())["spec"])
        data["id"] = guild_id or "semantic-" + uuid4().hex
        data["dependency_map"]["filesystem"]["properties"]["path_base"] = str(tmp_path)
        data["dependency_map"]["llm"] = {"class_name": LocalLLMResolver.get_qualified_class_name()}
        for spec in data["agents"]:
            if spec["id"] == "playwright_agent" and not real_scraper:
                spec["class_name"], spec["properties"] = Scraper.get_qualified_class_name(), {}
            if spec["id"] == "semantic_memory_coordinator":
                spec["properties"].update(config)
        builder = GuildBuilder.from_spec(GuildSpec.model_validate(data)).set_execution_engine(
            "rustic_ai.core.guild.execution." + engine
        )
        for id, topics in [("caller", ["user_message_broadcast"]), ("trace", ["sma.outcomes", "sma.results"])]:
            observer = (
                AgentBuilder(ProbeAgent)
                .set_id(id)
                .set_name(id)
                .set_description("Observer")
                .listen_to_default_topic(False)
                .add_additional_topic(topics[0])
            )
            for topic in topics[1:]:
                observer.add_additional_topic(topic)
            builder.add_agent_spec(observer.build_spec())
        for user in ["one", "two"]:
            builder.add_agent_spec(
                AgentBuilder(UserProxyAgent)
                .set_id("upa-" + user)
                .set_name("User " + user)
                .set_description("User entry")
                .set_properties({"user_id": user})
                .listen_to_default_topic(False)
                .add_additional_topic(UserProxyAgent.get_user_inbox_topic(user))
                .build_spec()
            )
        guild = builder.launch("semantic-tests")
        guilds.append(guild)
        coord = instance(guild, "semantic_memory_coordinator")
        assistant = instance(guild, "memory_assistant")
        llm = assistant._dependency_resolvers["llm"].get_or_resolve("semantic-tests", guild.id, "memory_assistant")
        fs = coord._dependency_resolvers["filesystem"].get_or_resolve("semantic-tests", guild.id, None)
        return guild, coord, assistant, instance(guild, "caller"), llm, instance(guild, "playwright_agent"), fs

    yield build
    for guild in guilds:
        guild.shutdown()


def send(guild, caller, text, user="one", msg_id=None, parts=None):
    payload = {"messages": [{"role": "user", "content": parts or text}]}
    inner = Message(
        id_obj=msg_id or caller._generate_id(Priority.NORMAL),
        topics="default_topic",
        sender=caller.get_agent_tag(),
        format=(
            ChatCompletionRequest.get_qualified_class_name()
            if hasattr(ChatCompletionRequest, "get_qualified_class_name")
            else "rustic_ai.core.guild.agent_ext.depends.llm.models.ChatCompletionRequest"
        ),
        payload=payload,
        recipient_list=[instance(guild, "semantic_memory_coordinator").get_agent_tag()],
    )
    caller.publish_dict(
        UserProxyAgent.get_user_inbox_topic(user), inner, format=Message, msg_id=GemstoneID.from_int(inner.id)
    )
    return inner


def outcome(caller):
    msgs = wait(caller.get_messages)
    assert len(msgs) == 1, [(m.topics, m.payload, m.recipient_list) for m in msgs]
    msg = msgs[0]
    caller.clear_messages()
    return msg


def native(assistant):
    return assistant.config.llm_request_wrappers[0]._uniko(assistant)


@pytest.mark.parametrize("engine", ENGINES)
def test_private_memory_original_identity_and_replay(launch, engine):
    guild, coord, assistant, caller, llm, _, _ = launch(engine=engine)
    inner = send(guild, caller, "I prefer tea to coffee")
    assert outcome(caller).process_status == "completed"
    record = native(assistant).data.message_sync(f"rustic-memory:user_assertion:{inner.id}:user")
    assert record.content.endswith("I prefer tea to coffee")
    send(guild, caller, "What drink do I prefer?")
    outcome(caller)
    assert "tea" in llm.calls[-1].model_dump_json()
    send(guild, caller, "What drink do I prefer?", user="two")
    outcome(caller)
    assert "tea" not in llm.calls[-1].model_dump_json()
    before = len(llm.calls)
    caller.publish_dict(
        UserProxyAgent.get_user_inbox_topic("one"), inner, format=Message, msg_id=GemstoneID.from_int(inner.id)
    )
    time.sleep(0.1)
    assert len(llm.calls) == before and not caller.get_messages() and not coord._requests


@pytest.mark.parametrize("rounds", [1, 2, 3])
def test_tool_rounds_pairing_and_no_internal_memory(launch, rounds):
    guild, coord, assistant, caller, llm, scraper, _ = launch()
    llm.responses = [response(None, [scrape_call(f"call-{i}")]) for i in range(rounds)] + [
        response("Harbor budget is CAD 42000.")
    ]
    inner = send(guild, caller, "Read the Harbor project budget")
    assert outcome(caller).process_status == "completed"
    assert len(scraper.calls) == rounds
    messages = llm.calls[-1].messages
    assert sum(m.role == "user" for m in messages) == 1
    assert next(m.content for m in messages if m.role == "user") == "Read the Harbor project budget"
    for i in range(rounds):
        assert any(m.role == "tool" and m.tool_call_id == f"call-{i}" and "42000" in m.content for m in messages)
    assert "example.test/harbor" in llm.calls[-1].model_dump_json()
    record = native(assistant).data.message_sync(f"rustic-memory:user_assertion:{inner.id}:user")
    assert record.content.endswith("Read the Harbor project budget")
    assert "scraped" not in record.content and not coord._requests


def test_failed_scrape_recovers_and_total_failure_cannot_answer(launch):
    guild, _, _, caller, llm, scraper, _ = launch()
    scraper.failures = [True, False]
    llm.responses = [
        response(None, [scrape_call("first")]),
        response(None, [scrape_call("second")]),
        response("Harbor CAD 42000"),
    ]
    send(guild, caller, "Fetch Harbor budget")
    assert outcome(caller).process_status == "completed"
    assert "scrape_failed" in llm.calls[1].model_dump_json()
    scraper.failures = [True]
    llm.responses = [response(None, [scrape_call()]), response("Fabricated grounded answer")]
    send(guild, caller, "Fetch Harbor again")
    assert outcome(caller).process_status == "error"


@pytest.mark.parametrize(
    "value",
    [
        response("truncated", finish="length"),
        response(None, [scrape_call(), scrape_call()]),
        response(None, [{"id": "bad", "type": "function", "function": {"name": "unknown", "arguments": "{}"}}]),
        RuntimeError("private provider error"),
    ],
)
def test_invalid_model_has_no_scrapes_or_memory(launch, value):
    guild, coord, assistant, caller, llm, scraper, _ = launch()
    llm.responses = [value]
    inner = send(guild, caller, "Fetch Harbor")
    assert outcome(caller).process_status == "error"
    assert not scraper.calls and not coord._requests
    assert native(assistant).data.message_sync(f"rustic-memory:user_assertion:{inner.id}:user") is None


def test_shared_documents_and_restart(launch):
    gid = "reopen-" + uuid4().hex
    guild, _, _, caller, llm, _, _ = launch(guild_id=gid)
    llm.responses = [response(None, [scrape_call()]), response("Harbor CAD 42000")]
    send(guild, caller, "Fetch Harbor project budget")
    outcome(caller)
    guild.shutdown()
    guild, _, _, caller, llm, _, _ = launch(guild_id=gid)
    send(guild, caller, "Harbor project budget", user="two")
    assert outcome(caller).process_status == "completed"
    assert "42000" in llm.calls[-1].model_dump_json()


def test_late_model_does_not_write_memory(launch):
    guild, coord, assistant, caller, llm, _, _ = launch(engine=ENGINES[1])
    send(guild, caller, "Warm up memory")
    outcome(caller)
    coord.config.deadline_seconds = 0.5
    before = len(llm.calls)

    def delayed(prompt):
        time.sleep(1)
        return response("Too late")

    llm.responses = [delayed]
    inner = send(guild, caller, "Hello")
    assert outcome(caller).process_status == "error"
    time.sleep(1)
    assert len(llm.calls) == before + 1
    assert native(assistant).data.message_sync(f"rustic-memory:user_assertion:{inner.id}:user") is None
    assert not caller.get_messages() and not coord._requests


def test_commit_failure_delivers_answer_warning(launch, monkeypatch):
    from rustic_ai.uniko_agent.memories import UnikoMemoriesStore

    guild, _, _, caller, llm, _, _ = launch()

    def fail(*args):
        raise RuntimeError("commit failed")

    monkeypatch.setattr(UnikoMemoriesStore, "commit", fail)
    send(guild, caller, "Hello")
    message = outcome(caller)
    assert message.process_status == "completed"
    assert "Accepted answer" in message.payload["text"] and "could not be confirmed" in message.payload["text"]


@pytest.mark.parametrize("engine", ENGINES)
def test_parallel_calls_out_of_order_duplicates_and_sender_guards(launch, engine):
    guild, coord, _, caller, llm, scraper, fs = launch(engine=engine)
    scraper.hold = True
    llm.responses = [response(None, [scrape_call("one"), scrape_call("two")]), response("Harbor CAD 42000")]
    send(guild, caller, "Fetch the Harbor budget")
    wait(lambda: len(scraper.calls) == 2)
    first, second = scraper.calls
    # An arbitrary sender with copied correlation cannot settle a call.
    caller.publish_dict(
        "sma.results",
        WebScrapingCompleted(id=first.payload.id, links=[]),
        format=WebScrapingCompleted,
        session_state=first.get_context(),
        routing_slip=caller.guild_spec.routes,
    )
    for ctx in [second, first]:
        name = uuid4().hex + ".md"
        with fs.open(name, "wb") as stream:
            stream.write(b"Harbor project budget CAD 42000.")
        value = WebScrapingCompleted(
            id=ctx.payload.id,
            links=[
                MediaLink(
                    url=name,
                    name=name,
                    mimetype="text/markdown",
                    on_filesystem=True,
                    metadata={"source_uri": ctx.payload.links[0].url},
                )
            ],
        )
        ctx.send(value)
        ctx.send(value)
    assert outcome(caller).process_status == "completed"
    tools = [m for m in llm.calls[-1].messages if m.role == "tool"]
    assert [m.tool_call_id for m in tools] == ["one", "two"]
    assert sum(len(m.content) for m in tools) <= 6000
    assert not coord._requests and not caller.get_messages()


def test_repeated_instruction_has_distinct_visible_turns(launch):
    guild, _, assistant, caller, _, _, _ = launch()
    first = send(guild, caller, "I prefer tea")
    outcome(caller)
    second = send(guild, caller, "I prefer tea")
    outcome(caller)
    assert first.id != second.id
    for request in [first, second]:
        assert native(assistant).data.message_sync(f"rustic-memory:user_assertion:{request.id}:user") is not None


@pytest.mark.parametrize("mode", ["failure", "lost_ack", "slow_commit"])
def test_commit_failure_timeout_and_late_completion_deliver_one_answer(launch, monkeypatch, mode):
    from rustic_ai.uniko_agent.conversation import ConversationMemoryCommitted
    from rustic_ai.uniko_agent.memories import UnikoMemoriesStore

    guild, coord, _, caller, _, _, _ = launch(engine=ENGINES[1], commit_timeout_seconds=0.1)
    if mode == "lost_ack":
        original = ProcessContext.send

        def send_without_ack(ctx, payload, *args, **kwargs):
            if isinstance(payload, ConversationMemoryCommitted):
                return None
            return original(ctx, payload, *args, **kwargs)

        monkeypatch.setattr(ProcessContext, "send", send_without_ack)
    elif mode == "slow_commit":
        original = UnikoMemoriesStore.commit

        def delayed(store, *args):
            time.sleep(0.4)
            return original(store, *args)

        monkeypatch.setattr(UnikoMemoriesStore, "commit", delayed)
    else:

        def fail(*args):
            raise RuntimeError("native finalize failed")

        monkeypatch.setattr(UnikoMemoriesStore, "commit", fail)
    send(guild, caller, "Remember tea")
    message = outcome(caller)
    assert message.process_status == "completed" and "Accepted answer" in message.payload["text"]
    assert "could not be confirmed" in message.payload["text"]
    time.sleep(0.5)
    assert not caller.get_messages() and not coord._requests


@pytest.mark.parametrize("bad", ["{bad json", "[]", '{"links":[]}', '{"links":[{"url":"file:///private"}]}'])
def test_malformed_tool_arguments_never_dispatch(launch, bad):
    guild, _, _, caller, llm, scraper, _ = launch()
    call = scrape_call()
    call["function"]["arguments"] = bad
    llm.responses = [response(None, [call])]
    send(guild, caller, "Fetch Harbor")
    assert outcome(caller).process_status == "error" and not scraper.calls


def test_scrape_round_exhaustion(launch):
    guild, _, assistant, caller, llm, scraper, _ = launch()
    llm.responses = [response(None, [scrape_call(str(i))]) for i in range(4)]
    request = send(guild, caller, "Fetch Harbor")
    assert outcome(caller).process_status == "error" and len(scraper.calls) == 3
    assert native(assistant).data.message_sync(f"rustic-memory:user_assertion:{request.id}:user") is None


def test_local_upload_partial_failure_and_file_only(launch):
    guild, _, assistant, caller, llm, _, fs = launch()
    with fs.open("budget.md", "wb") as stream:
        stream.write(b"Harbor project budget CAD 42000.")
    parts = [
        {"type": "text", "text": "Harbor project budget"},
        {
            "type": "file_url",
            "file_url": {"url": "file:///budget.md", "filename": "budget.md", "mime_type": "text/markdown"},
        },
        {"type": "file_url", "file_url": {"url": "missing.md", "filename": "missing.md"}},
    ]
    request = send(guild, caller, "", parts=parts)
    assert outcome(caller).process_status == "completed"
    assert "42000" in llm.calls[-1].model_dump_json()
    assert (
        native(assistant)
        .data.message_sync(f"rustic-memory:user_assertion:{request.id}:user")
        .content.endswith("Harbor project budget")
    )
    previous = len(llm.calls)
    send(guild, caller, "", parts=parts[1:2])
    message = outcome(caller)
    assert message.process_status == "completed" and "Stored 1, searchable 1" in message.payload["text"]
    assert len(llm.calls) == previous
    assert "warning" not in message.payload
    structured = [
        m.payload for m in instance(guild, "trace").get_messages() if m.format.endswith("SemanticMemoryAssistantResult")
    ][-1]
    assert structured["memory_status"] == "not_requested" and structured["warning"] is None


def test_zero_choices_is_terminal_without_unhandled_error(launch):
    guild, _, _, caller, llm, scraper, _ = launch()
    llm.responses = [ChatCompletionResponse(id="empty", created=1, model="local-test", choices=[])]
    send(guild, caller, "Hello")
    assert outcome(caller).process_status == "error" and not scraper.calls


def test_real_browser_partial_fetch_native_evidence_and_answer(launch):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import threading

    class Page(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(404 if self.path == "/missing" else 200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><title>Harbor</title><body>Harbor project budget is CAD 42000. Mina Patel coordinates Harbor.</body></html>"
            )

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Page)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        guild, _, _, caller, llm, _, _ = launch(real_scraper=True)
        url = f"http://127.0.0.1:{server.server_port}"
        call = scrape_call()
        call["function"]["arguments"] = json.dumps(
            {"links": [{"url": url + "/harbor"}, {"url": url + "/missing"}], "output_format": "text/markdown"}
        )
        llm.responses = [response(None, [call]), response("Harbor CAD 42000")]
        send(guild, caller, "Fetch Harbor project budget")
        final = outcome(caller)
        assert final.process_status == "completed", final.payload
        assert "42000" in llm.calls[-1].model_dump_json() and url in llm.calls[-1].model_dump_json()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


def test_blueprint_contract_and_public_outcomes():
    from pydantic import ValidationError

    from rustic_ai.showcase.semantic_memory_models import SemanticMemoryAssistantResult

    data = json.loads(BLUEPRINT.read_text())
    spec = GuildSpec.model_validate(data["spec"])
    assert data["version"] == "v2" and len(spec.agents) == 5
    assert all(not agent.listen_to_default_topic for agent in spec.agents)
    assert "kb_backend" not in spec.dependency_map
    terminal = [route for route in spec.routes.steps if route.process_status in {"completed", "error"}]
    assert len(terminal) == 4 and all(route.agent.id == "semantic_memory_coordinator" for route in terminal)
    assert sum(route.destination.topics == "user_message_broadcast" for route in terminal) == 2
    with pytest.raises(ValidationError):
        SemanticMemoryAssistantResult(request_id="r", answer="answer", memory_status="not-saved")


def test_private_conversation_reopens_and_stays_isolated(launch):
    gid = "private-reopen-" + uuid4().hex
    guild, _, _, caller, _, _, _ = launch(guild_id=gid)
    send(guild, caller, "My preferred drink is chamomile tea")
    outcome(caller)
    guild.shutdown()
    guild, _, _, caller, llm, _, _ = launch(guild_id=gid)
    send(guild, caller, "What drink do I prefer?")
    outcome(caller)
    assert "chamomile" in llm.calls[-1].model_dump_json()
    send(guild, caller, "What drink do I prefer?", user="two")
    outcome(caller)
    assert "chamomile" not in llm.calls[-1].model_dump_json()


def test_tool_call_ids_cannot_be_reused_between_rounds(launch):
    guild, _, assistant, caller, llm, scraper, _ = launch()
    llm.responses = [response(None, [scrape_call("same")]), response(None, [scrape_call("same")])]
    request = send(guild, caller, "Fetch Harbor project budget")
    assert outcome(caller).process_status == "error"
    assert len(scraper.calls) == 1
    assert native(assistant).data.message_sync(f"rustic-memory:user_assertion:{request.id}:user") is None


def test_terminal_scraper_exception_allows_recovery(launch):
    from rustic_ai.core.agents.commons.message_formats import ErrorMessage

    guild, _, _, caller, llm, scraper, _ = launch(engine=ENGINES[1])
    scraper.hold = True
    llm.responses = [
        response(None, [scrape_call("first")]),
        response(None, [scrape_call("recovery")]),
        response("Harbor CAD 42000"),
    ]
    send(guild, caller, "Fetch Harbor project budget")
    wait(lambda: scraper.calls)
    first = scraper.calls[0]
    scraper.hold = False
    first.send_error(
        ErrorMessage(
            agent_type=Scraper.get_qualified_class_name(),
            error_type="UNHANDLED_EXCEPTION",
            error_message="Endpoint failed",
        )
    )
    assert outcome(caller).process_status == "completed"
    assert len(scraper.calls) == 2


def test_long_source_metadata_preserves_required_evidence(launch):
    guild, coord, assistant, caller, llm, scraper, fs = launch()
    scraper.hold = True
    llm.responses = [response(None, [scrape_call()]), response("Answer accepted without its required evidence")]
    send(guild, caller, "Fetch Harbor budget")
    wait(lambda: scraper.calls)
    ctx = scraper.calls[0]
    links = []
    for i in range(8):
        filename = f"page-{i}.md"
        with fs.open(filename, "wb") as stream:
            stream.write(b"UNIQUE_FACT Harbor project budget is CAD 42000.")
        links.append(
            MediaLink(
                url=filename,
                name=filename,
                mimetype="text/markdown",
                on_filesystem=True,
                metadata={"source_uri": f"https://example.test/{i}/" + ("long-path-" * 110)},
            )
        )
    ctx.send(WebScrapingCompleted(id=ctx.payload.id, links=links))
    final = outcome(caller)
    tool = next(m for m in llm.calls[-1].messages if m.role == "tool")
    assert "UNIQUE_FACT" in tool.content and '"evidence"' in tool.content
    from rustic_ai.showcase.semantic_memory import _EVIDENCE_HEADER

    assert json.loads(tool.content.removeprefix(_EVIDENCE_HEADER))["evidence"]
    assert final.process_status == "completed"


def test_duplicate_scrape_errors_preserve_successful_source_outcomes(launch):
    from rustic_ai.core.agents.commons.message_formats import ErrorMessage
    from rustic_ai.core.utils import Priority

    guild, coord, assistant, caller, llm, scraper, fs = launch()
    scraper.hold = True
    llm.responses = [response(None, [scrape_call()]), response("Harbor budget CAD 42000")]
    send(guild, caller, "Fetch Harbor budget")
    wait(lambda: scraper.calls)
    ctx = scraper.calls[0]
    error = ErrorMessage(
        agent_type=scraper.get_qualified_class_name(), error_type="HTTP_ERROR_404", error_message="Not found"
    )
    message_id = scraper._generate_id(Priority.NORMAL)
    for _ in range(32):
        from rustic_ai.core.agents.testutils.probe_agent import PublishMixin

        PublishMixin.publish_dict(
            scraper,
            "sma.results",
            error,
            format=ErrorMessage,
            msg_id=message_id,
            session_state=ctx.get_context(),
            routing_slip=scraper.guild_spec.routes,
        )
    with fs.open("good.md", "wb") as stream:
        stream.write(b"Harbor budget is CAD 42000.")
    ctx.send(
        WebScrapingCompleted(
            id=ctx.payload.id,
            links=[
                MediaLink(
                    url="good.md",
                    name="good.md",
                    mimetype="text/markdown",
                    on_filesystem=True,
                    metadata={"source_uri": "https://example.test/good"},
                )
            ],
        )
    )
    final = outcome(caller)
    structured = [
        m.payload for m in instance(guild, "trace").get_messages() if m.format.endswith("SemanticMemoryAssistantResult")
    ][-1]
    assert final.process_status == "completed"
    assert len(structured["sources"]) == 2
    assert [s["status"] for s in structured["sources"]] == ["failed", "ingested"]


@pytest.mark.parametrize("image_kind", ["remote", "local", "data"])
@pytest.mark.parametrize("text", ["Describe this picture", ""])
def test_images_reach_model_and_only_actual_text_is_recorded(launch, image_kind, text):
    import base64

    guild, _, assistant, caller, llm, _, fs = launch()
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jE1cAAAAASUVORK5CYII="
    )
    with fs.open("picture.png", "wb") as stream:
        stream.write(png)
    urls = {
        "remote": "https://example.test/picture.png",
        "local": "file:///picture.png",
        "data": "data:image/png;base64," + base64.b64encode(png).decode(),
    }
    parts = ([{"type": "text", "text": text}] if text else []) + [
        {"type": "image_url", "image_url": {"url": urls[image_kind]}}
    ]
    request = send(guild, caller, text, parts=parts)
    assert outcome(caller).process_status == "completed"
    assert len(llm.calls) == 1
    content = next(m.content for m in llm.calls[0].messages if m.role == "user")
    assert any(part.type == "image_url" for part in content.root)
    structured = [
        m.payload for m in instance(guild, "trace").get_messages() if m.format.endswith("SemanticMemoryAssistantResult")
    ][-1]
    if text:
        record = native(assistant).data.message_sync(f"rustic-memory:user_assertion:{request.id}:user")
        assert record.content.endswith(text) and "picture.png" not in record.content
        assert structured["memory_status"] == "saved"
    else:
        assert structured["memory_status"] == "not_requested" and structured["warning"] is None


def test_parallel_acquisition_checks_budget_before_staging(launch, monkeypatch):
    import asyncio

    import rustic_ai.showcase.semantic_memory as workflow

    guild, coord, _, caller, _, _, fs = launch()
    coord.config.max_source_bytes = coord.config.max_workflow_bytes = 10
    origin = Message(
        id_obj=caller._generate_id(Priority.NORMAL),
        sender=caller.get_agent_tag(),
        topics="sma.requests",
        format="dict",
        payload={"query": "query"},
    )
    state = workflow._Turn(
        "budget", "1", "a", origin, "query", [], time.monotonic() + 60, int((time.time() + 60) * 1000)
    )
    coord._requests[state.key] = state
    for name in ["one.md", "two.md"]:
        with fs.open(name, "wb") as stream:
            stream.write(b"12345678")
    budgets = []
    original = workflow.acquire_document_source

    async def delayed(*args, **kwargs):
        budgets.append(args[3])
        await asyncio.sleep(0.1)
        return await original(*args, **kwargs)

    monkeypatch.setattr(workflow, "acquire_document_source", delayed)
    reader = coord._dependency_resolvers["upload_reader"].get_or_resolve("semantic-tests", guild.id, coord.id)

    async def run():
        return await asyncio.gather(
            coord._acquire(state, [{"url": "one.md"}], fs, reader),
            coord._acquire(state, [{"url": "two.md"}], fs, reader),
        )

    results = asyncio.run(run())
    assert budgets == [10, 2]
    assert sum(len(fs.cat_file(p)) for p in fs.find("documents/uploads")) == 8
    assert sum(len(sources) for sources, errors in results) == 1
    assert state.used_bytes == 8 and not state.acquisition_gate.locked()


@pytest.mark.parametrize("count", [1, 4])
def test_evidence_is_complete_json_within_character_and_token_budget(count):
    from rustic_ai.showcase.semantic_memory import (
        _EVIDENCE_HEADER,
        SemanticMemoryAssistantCoordinatorAgent,
    )
    from rustic_ai.uniko_agent.memories import tokenizer

    value = {
        "sources": [{"source_id": "source-1", "source_uri": "https://example.test/" + "x" * 1000}],
        "evidence": [{"source_id": "source-1", "content": "Harbor budget CAD 42000. " * 2000}],
    }
    rendered, usable = SemanticMemoryAssistantCoordinatorAgent._render_evidence(value, 6000 // count, 2000 // count)
    data = json.loads(rendered.removeprefix(_EVIDENCE_HEADER))
    assert usable and "42000" in data["evidence"][0]["content"] and data["partial"]
    assert data["evidence"][0]["source_id"] == "source-1"
    assert len(rendered) <= 6000 // count
    assert len(tokenizer().encode(rendered, disallowed_special=())) <= 2000 // count
    empty, usable = SemanticMemoryAssistantCoordinatorAgent._render_evidence({"evidence": [{"content": " "}]})
    assert not usable and json.loads(empty.removeprefix(_EVIDENCE_HEADER))["evidence"] == []


@pytest.mark.parametrize("text", ["Compare this image to the Harbor budget", ""])
def test_images_and_documents_are_processed_separately(launch, text):
    guild, _, _, caller, llm, _, fs = launch()
    with fs.open("budget.md", "wb") as stream:
        stream.write(b"Harbor budget CAD 42000.")
    parts = ([{"type": "text", "text": text}] if text else []) + [
        {"type": "image_url", "image_url": {"url": "https://example.test/harbor.png"}},
        {"type": "file_url", "file_url": {"url": "budget.md", "filename": "budget.md", "mime_type": "text/markdown"}},
    ]
    send(guild, caller, text, parts=parts)
    assert outcome(caller).process_status == "completed" and len(llm.calls) == 1
    content = next(m.content for m in llm.calls[0].messages if m.role == "user")
    assert any(part.type == "image_url" for part in content.root)
    assert all(part.type != "file_url" for part in content.root)
    structured = [
        m.payload for m in instance(guild, "trace").get_messages() if m.format.endswith("SemanticMemoryAssistantResult")
    ][-1]
    assert structured["sources"][0]["status"] == "ingested"
    assert "42000" in llm.calls[0].model_dump_json()
    assert structured["memory_status"] == ("saved" if text else "not_requested")


def test_image_only_tool_round_does_not_invent_a_user_assertion(launch):
    guild, _, _, caller, llm, _, _ = launch()
    llm.responses = [response(None, [scrape_call()]), response("Harbor budget CAD 42000")]
    send(guild, caller, "", parts=[{"type": "image_url", "image_url": {"url": "https://example.test/harbor.png"}}])
    assert outcome(caller).process_status == "completed"
    assert "42000" in next(m.content for m in llm.calls[-1].messages if m.role == "tool")
    structured = [
        m.payload for m in instance(guild, "trace").get_messages() if m.format.endswith("SemanticMemoryAssistantResult")
    ][-1]
    assert structured["memory_status"] == "not_requested" and structured["warning"] is None
