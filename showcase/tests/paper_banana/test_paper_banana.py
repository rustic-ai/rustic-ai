"""Execute the shipped routes with deterministic providers and native memory."""

import base64
from copy import deepcopy
import json
from pathlib import Path
import time
from uuid import uuid4

from pydantic import ValidationError
import pytest

from rustic_ai.core.agents.commons.image_generation import ImageGenerationResponse
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
from rustic_ai.core.ui_protocol.types import (
    FilesWithTextFormat,
    ImageFormat,
    TextFormat,
)
from rustic_ai.core.utils import Priority
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.showcase.paper_banana_models import (
    PaperBananaCritique,
    PaperBananaResult,
)
from rustic_ai.uniko_agent import (
    IngestDocumentRequest,
    IngestOutcome,
    MemoryAgentError,
    RecallItem,
    RecallRequest,
    RecallResponse,
)
from rustic_ai.vertexai.agents.image_generation import VertexAiImageGenerationRequest

BLUEPRINT = Path(__file__).parents[2] / "apps/paper_banana_guild.json"
ENGINES = ["sync.sync_exec_engine.SyncExecutionEngine", "multithreaded.multithreaded_exec_engine.MultiThreadedEngine"]
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a1ioAAAAASUVORK5CYII=")


def response(text, finish="stop"):
    return ChatCompletionResponse(
        id="deterministic",
        created=1,
        model="local-test",
        choices=[
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": finish,
            }
        ],
    )


class LocalLLM(LLM):
    def __init__(self, role):
        self.role = role
        self.calls = []
        self.verdicts = []
        self.fail = False
        self.finish = "stop"
        self.text = None

    @property
    def model(self):
        return "local-test"

    def get_config(self):
        return {}

    def completion(self, prompt, model=None):
        self.calls.append(prompt)
        if self.fail:
            raise RuntimeError("Endpoint unavailable")
        if self.text is not None:
            text = self.text
        elif self.role == "critic_agent":
            verdict = self.verdicts.pop(0) if self.verdicts else "approve"
            text = json.dumps({"verdict": verdict, "feedback": "Keep the scientific labels and improve spacing."})
        else:
            text = "Publication-ready Harbor diagram with a labeled budget of CAD 42000."
        return response(text, self.finish)

    async def async_completion(self, prompt, model=None):
        return self.completion(prompt, model)


class LocalLLMResolver(DependencyResolver[LLM]):
    def resolve(self, org_id, guild_id, agent_id):
        return LocalLLM(agent_id)


class Renderer(Agent):
    def __init__(self):
        self.calls = []
        self.hold = False
        self.fail = False

    @processor(VertexAiImageGenerationRequest, depends_on=["filesystem:guild_fs:guild"])
    def draw(self, ctx: ProcessContext[VertexAiImageGenerationRequest], guild_fs):
        self.calls.append(ctx)
        if self.hold:
            return
        if self.fail:
            ctx.send(ImageGenerationResponse(errors=["Image endpoint failed"]))
            return
        name = f"render-{len(self.calls)}.png"
        with guild_fs.open(name, "wb") as stream:
            stream.write(PNG)
        ctx.send(ImageGenerationResponse(files=[MediaLink(url=name, mimetype="image/png", on_filesystem=True)]))


class ControlledMemory(Agent):
    def __init__(self):
        self.ingestions = []
        self.recalls = []

    @processor(IngestDocumentRequest, depends_on=["filesystem:guild_fs:guild"])
    def ingest(self, ctx: ProcessContext[IngestDocumentRequest], guild_fs):
        self.ingestions.append(ctx)
        if ctx.payload.source.base64_data:
            content = base64.b64decode(ctx.payload.source.base64_data)
        else:
            with guild_fs.open(ctx.payload.source.media_link.url, "rb") as stream:
                content = stream.read()
        if content.startswith(b"hold"):
            return
        if content.startswith(b"fail"):
            ctx.send_error(MemoryAgentError(error="document_ingest_failed", message="Rejected"))
        else:
            ctx.send(
                IngestOutcome(
                    record_id=ctx.payload.record_id, stored=True, searchable=not content.startswith(b"archive")
                )
            )

    @processor(RecallRequest)
    def recall(self, ctx: ProcessContext[RecallRequest]):
        self.recalls.append(ctx)
        if ctx.payload.query == "recall-error":
            ctx.send_error(MemoryAgentError(error="recall_failed", message="Failed"))
            return
        sources = ctx.payload.scope.sources
        items = (
            []
            if ctx.payload.query == "empty"
            else [
                RecallItem(
                    node_id=1,
                    kind="Chunk",
                    content="Harbor project budget is CAD 42000.",
                    score=0.9,
                    sources=[],
                    source_id=sources[0] if sources else "prior-source",
                    source_ids=sources or ["prior-source"],
                    record_kind="external_evidence",
                    token_count=10,
                )
            ]
        )
        ctx.send(
            RecallResponse(
                items=items, total_tokens=10 if items else 0, phase1_only=False, phase2_only=False, coverage=1.0
            )
        )


def instance(guild, agent_id):
    wrapper = guild.execution_engine.agent_tracker.get_agent_wrapper(guild.id, agent_id)
    if hasattr(wrapper, "initialization_complete"):
        assert wrapper.initialization_complete.wait(5)
    return wrapper.agent


def wait(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.01)
    raise AssertionError("Expected workflow event did not arrive")


@pytest.fixture
def launch(tmp_path):
    guilds = []

    def build(native=False, engine=ENGINES[0], guild_id=None, origins=None, proxy=False, **config):
        data = deepcopy(json.loads(BLUEPRINT.read_text())["spec"])
        data["id"] = guild_id or "paperbanana-" + uuid4().hex
        data["dependency_map"]["filesystem"]["properties"]["path_base"] = str(tmp_path)
        data["dependency_map"]["upload_reader"]["properties"]["allowed_origins"] = origins or []
        data["dependency_map"]["llm"] = {"class_name": LocalLLMResolver.get_qualified_class_name()}
        for spec in data["agents"]:
            if spec["id"] == "visualizer_agent":
                spec["class_name"], spec["properties"] = Renderer.get_qualified_class_name(), {}
            if spec["id"] == "memory_agent" and not native:
                spec["class_name"], spec["properties"] = ControlledMemory.get_qualified_class_name(), {}
            if spec["id"] == "paperbanana_coordinator":
                spec["properties"].update(config)
        builder = GuildBuilder.from_spec(GuildSpec.model_validate(data))
        builder.set_execution_engine("rustic_ai.core.guild.execution." + engine)
        builder.add_agent_spec(
            AgentBuilder(ProbeAgent)
            .set_id("caller")
            .set_name("Caller")
            .set_description("Local caller")
            .listen_to_default_topic(False)
            .add_additional_topic("user_message_broadcast")
            .build_spec()
        )
        builder.add_agent_spec(
            AgentBuilder(ProbeAgent)
            .set_id("trace_probe")
            .set_name("Trace")
            .set_description("Contract observer")
            .listen_to_default_topic(False)
            .add_additional_topic("paperbanana.results")
            .add_additional_topic("paperbanana.outcomes")
            .build_spec()
        )
        if proxy:
            builder.add_agent_spec(
                AgentBuilder(UserProxyAgent)
                .set_id("user_proxy")
                .set_name("User Proxy")
                .set_description("Local user entry point")
                .set_properties({"user_id": "researcher"})
                .listen_to_default_topic(False)
                .add_additional_topic(UserProxyAgent.get_user_inbox_topic("researcher"))
                .add_additional_topic("user_message_broadcast")
                .build_spec()
            )
        guild = builder.launch("paperbanana-tests")
        guilds.append(guild)
        coordinator = instance(guild, "paperbanana_coordinator")
        memory = instance(guild, "memory_agent")
        caller = instance(guild, "caller")
        filesystem = coordinator._dependency_resolvers["filesystem"].get_or_resolve("paperbanana-tests", guild.id, None)
        llms = {
            role: instance(guild, role)._dependency_resolvers["llm"].get_or_resolve("paperbanana-tests", guild.id, role)
            for role in ("planner_agent", "stylist_agent", "critic_agent")
        }
        return guild, coordinator, memory, caller, filesystem, llms, instance(guild, "visualizer_agent")

    yield build
    for guild in guilds:
        guild.shutdown()


def send(caller, payload, format=ChatCompletionRequest, **kwargs):
    caller.publish_dict("paperbanana.requests", payload, format=format, routing_slip=caller.guild_spec.routes, **kwargs)


def result(caller, timeout=5):
    messages = wait(caller.get_messages, timeout)
    assert len(messages) == 1
    message = messages[0]
    caller.clear_messages()
    assert message.process_status in {"completed", "error"}
    return message


def file_request(text=None, names=("reference.md",)):
    parts = [
        {"type": "file_url", "file_url": {"url": name, "filename": name, "mime_type": "text/markdown"}}
        for name in names
    ]
    if text:
        parts += [{"type": "text", "text": text}]
    return {"messages": [{"role": "user", "content": parts}]}


def write(fs, name, content=b"Harbor project budget is CAD 42000."):
    with fs.open(name, "wb") as stream:
        stream.write(content)


def test_blueprint_contract_and_public_schemas():
    data = json.loads(BLUEPRINT.read_text())
    spec = GuildSpec.model_validate(data["spec"])
    assert data["version"] == "v2"
    assert len(spec.agents) == 7
    assert "kb_backend" not in spec.dependency_map
    assert "KnowledgeAgent" not in spec.model_dump_json()
    assert all(not agent.listen_to_default_topic for agent in spec.agents)
    terminal = [route for route in spec.routes.steps if route.process_status in {"completed", "error"}]
    assert len(terminal) == 4 and all(route.agent.id == "paperbanana_coordinator" for route in terminal)
    assert sum(route.destination.topics == "user_message_broadcast" for route in terminal) == 2
    with pytest.raises(ValidationError):
        PaperBananaCritique(verdict="APPROVE", feedback="text")
    with pytest.raises(ValidationError):
        PaperBananaResult(request_id="r", kind="illustration")


@pytest.mark.parametrize("engine", ENGINES)
def test_text_only_latest_instruction_and_no_evidence_fallback(launch, engine):
    _, coord, memory, caller, _, llms, renderer = launch(engine=engine)
    send(
        caller,
        {
            "messages": [
                {"role": "user", "content": "outdated"},
                {"role": "assistant", "content": "past answer"},
                {"role": "user", "content": "empty"},
            ]
        },
    )
    message = result(caller)
    ImageFormat.model_validate(message.payload)
    assert memory.recalls[0].payload.query == "empty"
    prompt = llms["planner_agent"].calls[0].messages[-1].content
    assert "Original instruction:\nempty" in prompt and "No reference evidence" in prompt
    assert "outdated" not in prompt
    assert len(renderer.calls) == 1
    assert not coord._requests
    assert not caller.get_messages()


def test_upload_only_honest_partial_and_archival_counts(launch):
    _, coord, memory, caller, fs, llms, renderer = launch()
    write(fs, "good.md")
    write(fs, "archival.pdf", b"archive document")
    write(fs, "bad.md", b"fail document")
    send(caller, file_request(names=("good.md", "archival.pdf", "bad.md", "missing.md")))
    message = result(caller)
    text = TextFormat.model_validate(message.payload).text
    assert "Stored 2, searchable 1, failed 2, unknown 0" in text
    assert not memory.recalls and not renderer.calls
    assert not any(llm.calls for llm in llms.values())
    assert not coord._requests


@pytest.mark.parametrize("engine", ENGINES)
def test_upload_instruction_uses_only_successful_sources_and_retains_metadata(launch, engine):
    _, coord, memory, caller, fs, llms, _ = launch(engine=engine)
    write(fs, "good.md")
    write(fs, "bad.md", b"fail document")
    send(caller, file_request("Illustrate the Harbor budget", ("missing.md", "good.md", "bad.md")))
    message = result(caller)
    assert message.process_status == "completed"
    assert "failed 2" in ImageFormat.model_validate(message.payload).description
    assert len(memory.recalls[0].payload.scope.sources) == 1
    assert memory.recalls[0].payload.scope.sessions == ["corpus:paperbanana:references"]
    assert memory.ingestions[0].payload.source.path_hint == "good.md"
    assert memory.ingestions[0].payload.source.mime_type == "text/markdown"
    prompt = llms["planner_agent"].calls[0].messages[-1].content
    assert "Illustrate the Harbor budget" in prompt and "42000" in prompt
    assert memory.recalls[0].payload.scope.sources[0] in prompt
    assert not coord._requests


@pytest.mark.parametrize("content", [b"fail document", b"archive document"])
def test_no_usable_upload_fails_before_recall_or_planning(launch, content):
    _, _, memory, caller, fs, llms, renderer = launch()
    write(fs, "reference.md", content)
    send(caller, file_request("Use this reference"))
    assert result(caller).process_status == "error"
    assert not memory.recalls and not renderer.calls
    assert not any(llm.calls for llm in llms.values())


def test_ui_files_and_base64_parts(launch):
    _, _, memory, caller, fs, _, _ = launch()
    write(fs, "reference.md")
    send(caller, {"files": [{"name": "Original.md", "url": "reference.md"}], "text": None}, format=FilesWithTextFormat)
    assert result(caller).process_status == "completed"
    assert memory.ingestions[0].payload.source.path_hint == "Original.md"
    send(
        caller,
        {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "file",
                            "file": {
                                "filename": "Inline.md",
                                "file_data": "data:text/markdown;base64," + base64.b64encode(b"Harbor 42000").decode(),
                            },
                        }
                    ],
                }
            ]
        },
    )
    assert result(caller).process_status == "completed"
    assert memory.ingestions[-1].payload.source.mime_type == "text/markdown"


@pytest.mark.parametrize(
    "verdicts,expected,images",
    [(["approve"], "completed", 1), (["reject", "approve"], "completed", 2), (["reject"] * 3, "error", 3)],
)
def test_critique_refinement_is_bounded_and_only_one_result(launch, verdicts, expected, images):
    _, coord, _, caller, _, llms, renderer = launch()
    llms["critic_agent"].verdicts = list(verdicts)
    send(caller, {"messages": [{"role": "user", "content": "Draw Harbor"}]})
    assert result(caller).process_status == expected
    assert len(renderer.calls) == images
    assert len(llms["planner_agent"].calls) == 1
    assert len(llms["stylist_agent"].calls) == images
    assert not coord._requests and not caller.get_messages()
    critique = llms["critic_agent"].calls[0]
    assert critique.response_format["json_schema"]["schema"] == PaperBananaCritique.model_json_schema()
    assert critique.messages[-1].content.root[-1].image_url.url.startswith("data:image/png;base64,")


@pytest.mark.parametrize(
    "role,mode", [("critic_agent", "malformed"), ("planner_agent", "truncated"), ("stylist_agent", "failure")]
)
def test_invalid_or_failed_model_output_is_terminal(launch, role, mode):
    _, coord, _, caller, _, llms, renderer = launch()
    if mode == "malformed":
        llms[role].text = "I do NOT APPROVE this image"
    elif mode == "truncated":
        llms[role].finish = "length"
    else:
        llms[role].fail = True
    send(caller, {"messages": [{"role": "user", "content": "Draw Harbor"}]})
    assert result(caller).process_status == "error"
    assert len(renderer.calls) == (1 if mode == "malformed" else 0)
    assert not coord._requests


def test_renderer_and_recall_failure_are_terminal(launch):
    _, _, _, caller, _, _, renderer = launch()
    renderer.fail = True
    send(caller, {"messages": [{"role": "user", "content": "Draw Harbor"}]})
    assert result(caller).process_status == "error"
    renderer.fail = False
    send(caller, {"messages": [{"role": "user", "content": "recall-error"}]})
    assert result(caller).process_status == "error"
    assert len(renderer.calls) == 1


def test_timeout_capacity_duplicates_and_late_images(launch):
    _, coord, _, caller, _, _, renderer = launch(deadline_seconds=1.0, max_active_requests=1)
    renderer.hold = True
    request = {"messages": [{"role": "user", "content": "Draw Harbor"}]}
    msg_id = caller._generate_id(Priority.NORMAL)
    send(caller, request, msg_id=msg_id)
    wait(lambda: renderer.calls)
    send(caller, request, msg_id=msg_id)
    assert len(renderer.calls) == 1
    send(caller, request)
    assert "Capacity exceeded" in result(caller).payload["text"]
    assert "Workflow timed out" in result(caller).payload["text"]
    renderer.calls[0].send(ImageGenerationResponse(files=[MediaLink(url="late.png", on_filesystem=True)]))
    send(caller, request, msg_id=msg_id)
    assert not caller.get_messages() and not coord._requests


def test_source_size_invalid_input_and_original_context_bounds(launch):
    _, coord, memory, caller, fs, _, _ = launch(max_source_bytes=8, max_workflow_bytes=8)
    write(fs, "reference.md", b"long document over limit")
    send(caller, file_request())
    assert result(caller).process_status == "error" and not memory.ingestions
    send(caller, {"messages": [{"role": "user", "content": "x" * 4001}]})
    assert result(caller).process_status == "error"
    send(
        caller,
        {"messages": [{"role": "user", "content": "Draw"}]},
        session_state={
            "original_attachment": {"file_data": "secret"},
            "headers": {"Authorization": "secret"},
            "trace_id": "keep",
        },
    )
    result(caller)
    context = memory.recalls[0].get_context()
    assert context["trace_id"] == "keep" and "headers" not in context and "original_attachment" not in context
    assert not coord._requests


def text_pdf(text=""):
    body = f"BT /F1 12 Tf 10 100 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 400 200] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(body)} >>\nstream\n".encode() + body + b"\nendstream",
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


@pytest.mark.parametrize("engine", ENGINES)
def test_native_pdf_evidence_scoping_and_persistent_reopen(launch, engine):
    guild_id = "native-" + uuid4().hex
    guild, coord, _, caller, fs, llms, _ = launch(native=True, engine=engine, guild_id=guild_id)
    write(fs, "old.md", b"Old Harbor budget is CAD 99999.")
    send(caller, file_request(names=("old.md",)))
    assert result(caller, 120).process_status == "completed"
    write(fs, "harbor.pdf", text_pdf("Harbor project budget is CAD 42000. Mina Patel is coordinator."))
    write(fs, "blank.pdf", text_pdf())
    parts = [
        {"type": "file_url", "file_url": {"url": name, "filename": name, "mime_type": "application/pdf"}}
        for name in ("harbor.pdf", "blank.pdf")
    ]
    parts.append({"type": "text", "text": "Illustrate Harbor project budget and coordinator"})
    send(caller, {"messages": [{"role": "user", "content": parts}]})
    message = result(caller, 120)
    assert message.process_status == "completed", message.payload
    assert "Stored 2, searchable 1, failed 0" in message.payload["description"]
    prompt = llms["planner_agent"].calls[-1].messages[-1].content
    assert "42000" in prompt and "99999" not in prompt and "Mina" in prompt
    assert not coord._requests
    guild.shutdown()
    guild, coord, _, caller, fs, llms, _ = launch(native=True, engine=engine, guild_id=guild_id)
    send(caller, {"messages": [{"role": "user", "content": "Illustrate Harbor project budget coordinator"}]})
    assert result(caller, 120).process_status == "completed"
    assert "42000" in llms["planner_agent"].calls[-1].messages[-1].content
    send(caller, {"messages": [{"role": "user", "content": parts[:-1]}]})
    assert result(caller, 120).process_status == "completed"
    replay = [
        message
        for message in instance(guild, "trace_probe").get_messages()
        if message.format.endswith("DocumentWorkflowResult")
    ][-1]
    assert all(source["outcome"]["was_deduplicated"] for source in replay.payload["sources"])
    assert not coord._requests


@pytest.mark.parametrize("engine", ENGINES)
def test_out_of_order_duplicate_and_wrong_ingestion_acknowledgments(launch, engine):
    _, coord, memory, caller, fs, llms, renderer = launch(engine=engine)
    write(fs, "first.md", b"hold first")
    write(fs, "second.md", b"hold second")
    send(caller, file_request("Draw Harbor", ("first.md", "second.md")))
    wait(lambda: len(memory.ingestions) == 2)
    first, second = memory.ingestions
    second.send(IngestOutcome(record_id="wrong-record", stored=True, searchable=True))
    outcome = IngestOutcome(record_id=second.payload.record_id, stored=True, searchable=True)
    second.send(outcome)
    second.send(outcome)
    time.sleep(0.05)
    assert not memory.recalls and not llms["planner_agent"].calls and not caller.get_messages()
    first.send(IngestOutcome(record_id=first.payload.record_id, stored=True, searchable=True))
    assert result(caller).process_status == "completed"
    second.send(outcome)
    first.send(IngestOutcome(record_id=first.payload.record_id, stored=True, searchable=True))
    time.sleep(0.05)
    assert len(memory.recalls) == len(renderer.calls) == 1
    assert not coord._requests and not caller.get_messages()


@pytest.mark.parametrize("engine", ENGINES)
def test_in_flight_requests_and_stale_sender_attempt_iteration(launch, engine):
    _, coord, _, caller, fs, llms, renderer = launch(engine=engine)
    renderer.hold = True
    send(caller, {"messages": [{"role": "user", "content": "Draw first diagram"}]})
    send(caller, {"messages": [{"role": "user", "content": "Draw second diagram"}]})
    wait(lambda: len(renderer.calls) == 2)
    first, second = renderer.calls
    payload = ImageGenerationResponse(files=[MediaLink(url="render.png", on_filesystem=True)])
    # Same correlation with an untrusted sender cannot advance the stage.
    caller.publish_dict(
        "paperbanana.results",
        payload,
        format=ImageGenerationResponse,
        session_state=first.get_context(),
        routing_slip=caller.guild_spec.routes,
    )
    for key, value in (("paperbanana_attempt", "stale"), ("paperbanana_iteration", 99)):
        original = first.get_context()[key]
        first.update_context({key: value})
        first.send(payload)
        first.update_context({key: original})
    time.sleep(0.05)
    assert len(coord._requests) == 2 and not llms["critic_agent"].calls
    # Complete in reverse order; the instruction stays attached to its workflow.
    for ctx in (second, first):
        with fs.open("render.png", "wb") as stream:
            stream.write(PNG)
        ctx.send(payload)
        assert result(caller).process_status == "completed"
        ctx.send(payload)
    time.sleep(0.05)
    assert len(llms["critic_agent"].calls) == 2 and not caller.get_messages() and not coord._requests
    instructions = [call.model_dump()["messages"][-1]["content"][0]["text"] for call in llms["critic_agent"].calls]
    assert "Draw second diagram" in instructions[0] and "Draw first diagram" in instructions[1]


@pytest.mark.parametrize("format", [ChatCompletionRequest, TextFormat, FilesWithTextFormat])
def test_user_proxy_entry_routes(launch, format):
    guild, coord, _, caller, fs, _, _ = launch(proxy=True)
    if format is ChatCompletionRequest:
        payload = {"messages": [{"role": "user", "content": "Draw Harbor"}]}
    elif format is TextFormat:
        payload = {"text": "Draw Harbor"}
    else:
        write(fs, "reference.md")
        payload = {
            "text": "Draw Harbor",
            "files": [{"mediaLink": {"url": "reference.md", "name": "reference.md", "mimetype": "text/markdown"}}],
        }
    inner = Message(
        id_obj=caller._generate_id(Priority.NORMAL),
        topics="default_topic",
        sender=caller.get_agent_tag(),
        format=get_qualified_class_name(format),
        payload=payload,
        recipient_list=[coord.get_agent_tag()],
    )
    caller.publish(UserProxyAgent.get_user_inbox_topic("researcher"), inner)
    assert result(caller).process_status == "completed"
    assert not coord._requests
    assert instance(guild, "user_proxy")
