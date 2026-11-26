"""Exercise shipped research guilds through real routing and local persistence."""

import asyncio
from collections import Counter
import time
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from rustic_ai.core.agents.testutils import ProbeAgent
from rustic_ai.core.agents.utils.user_proxy_agent import UserProxyAgent
from rustic_ai.core.guild.agent_ext.depends import DependencyResolver
from rustic_ai.core.guild.agent_ext.depends.embeddings import Embeddings
from rustic_ai.core.guild.agent_ext.depends.llm import LLM
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
)
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.guild.dsl import GuildSpec
from rustic_ai.core.messaging import Message, Priority
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.showcase.catalog import load_blueprint

ENGINES = ["sync.sync_exec_engine.SyncExecutionEngine", "multithreaded.multithreaded_exec_engine.MultiThreadedEngine"]


class ResearchLLM(LLM):
    def __init__(self, role, calls):
        self.role, self.calls = role, calls

    @property
    def model(self):
        return "local-research"

    def get_config(self):
        return {}

    def completion(self, prompt, model=None):
        self.calls.append((self.role, prompt))
        if len(self.calls) > 30:
            raise RuntimeError("Research exceeded its routing bounds")
        content = "Harbor budget####Harbor pilot cost" if self.role == "query_agent" else "Harbor budget is CAD 42000."
        return ChatCompletionResponse(
            id=uuid4().hex,
            created=1,
            model=self.model,
            input_messages=prompt.messages,
            choices=[{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        )

    async def async_completion(self, prompt, model=None):
        return self.completion(prompt, model)


class ResearchLLMResolver(DependencyResolver[LLM]):
    calls: list[tuple[str, ChatCompletionRequest]] = []

    def resolve(self, org_id, guild_id, agent_id):
        return ResearchLLM(agent_id, self.calls)


class LocalEmbeddings(Embeddings):
    def embed(self, text):
        return [[1.0, 0.0, 0.0] for _ in text]


class LocalEmbeddingResolver(DependencyResolver[Embeddings]):
    def resolve(self, org_id, guild_id, agent_id):
        return LocalEmbeddings()


def wait_until(predicate, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(0.01)
    pytest.fail("Research catalog flow did not complete")


def instance(guild, name):
    wrapper = guild.execution_engine.agent_tracker.get_agent_wrapper(guild.id, name)
    if hasattr(wrapper, "initialization_complete"):
        assert wrapper.initialization_complete.wait(10)
    assert wrapper.agent is not None
    return wrapper.agent


@pytest.fixture
def research(tmp_path, monkeypatch):
    from rustic_ai.playwright import agent as browser_module
    from rustic_ai.serpapi import agent as search_module
    from rustic_ai.vertexai import client as google_module

    calls: list[tuple[str, ChatCompletionRequest]] = []
    searches, pages, google_calls = [], [], []
    guilds: list[Any] = []
    ResearchLLMResolver.calls = calls
    monkeypatch.setenv("SERP_API_KEY", "local-test")

    class Search:
        def search(self, params, **kwargs):
            searches.append(params)
            return {
                "search_metadata": {"status": "Success"},
                "organic_results": [
                    {"link": "https://research.example/harbor", "title": "Harbor", "snippet": "Budget", "position": 1}
                ],
            }

    monkeypatch.setattr(search_module.serpapi, "Client", lambda **kwargs: Search())

    def grounded(**kwargs):
        google_calls.append(kwargs)
        return SimpleNamespace(text="Harbor planning budget is CAD 42000.", candidates=[])

    monkeypatch.setattr(
        google_module.genai,
        "Client",
        lambda **kwargs: SimpleNamespace(models=SimpleNamespace(generate_content=grounded)),
    )

    class Page:
        def set_default_timeout(self, timeout):
            pass

        async def goto(self, url, **kwargs):
            pages.append(url)
            self.url = url
            return SimpleNamespace(status=200, url=url, headers={})

        async def title(self):
            return "Harbor official budget"

        async def content(self):
            return "<html><h1>Harbor</h1><p>Harbor budget is CAD 42000.</p></html>"

        async def close(self):
            pass

    class Context:
        async def new_page(self):
            return Page()

        async def close(self):
            pass

    class Browser:
        def is_connected(self):
            return True

        async def new_context(self, **kwargs):
            return Context()

        async def close(self):
            pass

    class Chromium:
        async def launch(self, **kwargs):
            return Browser()

    class Playwright:
        chromium = Chromium()

        async def start(self):
            return self

        async def stop(self):
            pass

    monkeypatch.setattr(browser_module, "async_playwright", Playwright)
    monkeypatch.setattr(browser_module, "install", lambda args: True)

    yield lambda name="uniko_research_guild.json", engine=ENGINES[0]: _launch_catalog(
        name, engine, tmp_path, guilds, calls, searches, pages, google_calls
    )
    for guild in reversed(guilds):
        guild.shutdown()


def _launch_catalog(name, engine, tmp_path, guilds, calls, searches, pages, google_calls):
    data = load_blueprint(name)["spec"]
    data["id"] = "research-" + uuid4().hex
    data["execution_engine"] = "rustic_ai.core.guild.execution." + engine
    dependencies = data.setdefault("dependency_map", {})
    dependencies["llm"] = {"class_name": ResearchLLMResolver.get_qualified_class_name()}
    dependencies["filesystem"] = {
        "class_name": "rustic_ai.core.guild.agent_ext.depends.filesystem.FileSystemResolver",
        "properties": {"protocol": "file", "path_base": str(tmp_path), "storage_options": {"auto_mkdir": True}},
    }
    if name == "uniko_research_guild.json":
        dependencies["uniko"] = {
            "class_name": "rustic_ai.uniko_agent.UnikoResolver",
            "properties": {"storage_path": "research.db", "streaming": False},
        }
    else:
        dependencies["embeddings"] = {"class_name": LocalEmbeddingResolver.get_qualified_class_name()}
        dependencies["vectorstore"]["properties"]["chroma_settings"]["persist_directory"] = str(tmp_path / data["id"])
    builder = GuildBuilder.from_spec(GuildSpec.model_validate(data))
    builder.add_agent_spec(
        AgentBuilder(UserProxyAgent)
        .set_id("upa-reader")
        .set_name("Entry")
        .set_description("User entry")
        .set_properties({"user_id": "reader"})
        .listen_to_default_topic(False)
        .add_additional_topic(UserProxyAgent.get_user_inbox_topic("reader"))
        .build_spec()
    )
    probe = (
        AgentBuilder(ProbeAgent)
        .set_id("observer")
        .set_name("Observer")
        .set_description("Research trace")
        .listen_to_default_topic(False)
    )
    for topic in [
        "user_message_broadcast",
        "research_coordinator",
        "memory_recall",
        "memory_observe",
        "memory_ingest",
        "default_topic",
        "error_topic",
        "system_topic",
    ]:
        probe.add_additional_topic(topic)
    builder.add_agent_spec(probe.build_spec())
    guild = builder.launch("research-tests")
    guilds.append(guild)
    observer = instance(guild, "observer")
    for spec in builder.build_spec().agents:
        instance(guild, spec.id)
    return guild, observer, calls, searches, pages, google_calls


def send(probe, text, file=None):
    parts = [{"type": "text", "text": text}]
    for path in ([file] if isinstance(file, str) else file or []):
        parts.append(
            {
                "type": "file_url",
                "file_url": {
                    "url": path,
                    "on_filesystem": True,
                    "filename": "Harbor reference.md",
                    "mime_type": "text/markdown",
                    "encoding": "utf-8",
                },
            }
        )
    payload = {"messages": [{"role": "user", "content": parts}]}
    inner = Message(
        id_obj=probe._generate_id(Priority.NORMAL),
        topics="default_topic",
        sender=probe.get_agent_tag(),
        format=get_qualified_class_name(ChatCompletionRequest),
        payload=payload,
    )
    probe.publish(UserProxyAgent.get_user_inbox_topic("reader"), inner)
    return inner


def terminal(probe):
    return [
        m
        for m in probe.get_messages()
        if m.topic_published_to == "user_message_broadcast" and m.sender.id == "research_coordinator"
    ]


@pytest.mark.parametrize("engine", ENGINES)
@pytest.mark.parametrize("entry", ["search", "url", "upload", "multiple_uploads"])
def test_uniko_catalog_full_flow_ingests_synthesizes_and_finalizes(research, engine, entry):
    guild, probe, calls, searches, pages, google_calls = research(engine=engine)
    memory = instance(guild, "memory_agent")
    fs = memory._dependency_resolvers["filesystem"].get_or_resolve("research-tests", guild.id, None)
    if entry in {"upload", "multiple_uploads"}:
        fs.pipe_file("uploads/harbor.md", b"Harbor budget is CAD 42000.")
    if entry == "multiple_uploads":
        fs.pipe_file("uploads/harbor-team.md", b"Harbor budget coordinator is Mina Patel.")
    send(
        probe,
        "Research Harbor budget" if entry != "url" else "What is the Harbor budget at https://research.example/harbor",
        (
            ["uploads/harbor.md", "uploads/harbor-team.md"]
            if entry == "multiple_uploads"
            else "uploads/harbor.md" if entry == "upload" else None
        ),
    )
    result = wait_until(lambda: terminal(probe))[0]
    assert result.process_status == "completed" and "42000" in result.payload["choices"][0]["message"]["content"]
    assert not instance(guild, "research_coordinator")._requests
    assert Counter(role for role, _ in calls) == (
        {"query_agent": 1, "synthesis_agent": 1} if entry == "search" else {"synthesis_agent": 1}
    )
    assert len(searches) == len(google_calls) == (2 if entry == "search" else 0)
    assert len(pages) == (0 if entry in {"upload", "multiple_uploads"} else 2 if entry == "search" else 1)
    synthesis = next(prompt for role, prompt in calls if role == "synthesis_agent")
    assert "42000" in synthesis.model_dump_json() and "Original question:" in synthesis.model_dump_json()
    trace = probe.get_messages()
    ingestions = [m for m in trace if m.format.endswith("IngestOutcome")]
    assert len(ingestions) == (2 if entry in {"search", "multiple_uploads"} else 1)
    assert all(m.payload["stored"] and m.payload["searchable"] for m in ingestions)
    if entry in {"upload", "multiple_uploads"}:
        requests = [m for m in trace if m.format.endswith("IngestDocumentRequest")]
        assert all(m.payload["media_link"]["on_filesystem"] for m in requests)
        assert all(m.payload["media_link"]["name"] == "Harbor reference.md" for m in requests)
        assert all(m.payload["media_link"]["mimetype"] == "text/markdown" for m in requests)
    if entry == "multiple_uploads":
        assert "Mina Patel" in synthesis.model_dump_json()
    assert any(m.format.endswith("FinalizeMemorySessionResult") and m.payload["rebuilt"] for m in trace)
    assert any(m.format.endswith("RecallResponse") and m.payload["items"] for m in trace)
    native = memory._dependency_resolvers["uniko"].get_or_resolve("research-tests", guild.id, memory.id)

    async def artifacts():
        return await native.query("MATCH (a:Artifact) RETURN id(a) AS id")

    assert asyncio.run(artifacts())
    # A late native completion cannot reopen a settled coordinator request.
    late = next(m for m in trace if m.format.endswith("FinalizeMemorySessionResult"))
    probe._client.publish(late.model_copy(deep=True))
    time.sleep(0.05)
    assert len(terminal(probe)) == 1


@pytest.mark.parametrize("engine", ENGINES)
def test_generic_researcher_catalog_indexes_scraped_documents_and_answers(research, engine):
    guild, probe, calls, searches, pages, _ = research("researcher.json", engine)
    send(probe, "Research Harbor budget")

    def final():
        return [
            m
            for m in probe.get_messages()
            if m.topic_published_to == "user_message_broadcast" and m.format.endswith("TextFormat")
        ]

    result = wait_until(final)[0]
    assert "42000" in result.payload["text"]
    assert len(calls) == len(searches) == len(pages) == 1
    prompt = calls[0][1].model_dump_json()
    assert "42000" in prompt and "Context:" in prompt
    vector_id = next(spec.id for spec in probe.guild_spec.agents if spec.name == "Vector Agent")
    vector = instance(guild, vector_id)
    store = vector._dependency_resolvers["vectorstore"].get_or_resolve("research-tests", guild.id, None)
    assert store.collection.count() > 0
    time.sleep(0.05)
    assert len(final()) == 1
