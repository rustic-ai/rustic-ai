"""Run authored conversation guilds with real agents and deterministic model services."""

from collections import Counter
import json
import re
import time
from uuid import uuid4

import pytest

from rustic_ai.core.agents.testutils import ProbeAgent
from rustic_ai.core.agents.utils.user_proxy_agent import UserProxyAgent
from rustic_ai.core.guild.agent_ext.depends import DependencyResolver
from rustic_ai.core.guild.agent_ext.depends.llm.llm import LLM
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
)
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.guild.dsl import GuildSpec
from rustic_ai.core.messaging import Message, Priority
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.showcase.catalog import load_blueprint


class ConversationLLM(LLM):
    def __init__(self, role, calls):
        self.role, self.calls = role, calls

    @property
    def model(self):
        return "local-conversation"

    def get_config(self):
        return {}

    def completion(self, prompt, model=None):
        self.calls.append((self.role, prompt))
        if len(self.calls) > 30:
            raise RuntimeError("Conversation exceeded its routing bounds")
        content = f"Harbor answer from {self.role}"
        if self.role.startswith("actor_"):
            content += "\n**Belief:** Harbor budgets are published"
        if self.role == "classifier_agent":
            content = "vertex_ai/local-third"
        return ChatCompletionResponse(
            id=uuid4().hex,
            created=1,
            model=self.model,
            input_messages=prompt.messages,
            choices=[{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        )

    async def async_completion(self, prompt, model=None):
        return self.completion(prompt, model)


class ConversationResolver(DependencyResolver[LLM]):
    calls: list[tuple[str, ChatCompletionRequest]] = []

    def resolve(self, org_id, guild_id, agent_id):
        return ConversationLLM(agent_id, self.calls)


def render(name):
    envelope = load_blueprint(name)
    values = envelope["spec"].get("configuration", {})
    text = json.dumps(envelope["spec"])
    return json.loads(re.sub(r"\{\{\s*(\w+)\s*\}\}", lambda m: str(values[m[1]]), text))


@pytest.fixture
def conversation(database):
    guilds = []

    def launch(name, engine=None):
        data = render(name)
        data["id"] = "conversation-" + uuid4().hex
        if engine:
            data.setdefault("properties", {})["execution_engine"] = engine
        calls: list[tuple[str, ChatCompletionRequest]] = []
        ConversationResolver.calls = calls
        resolver = {"class_name": ConversationResolver.get_qualified_class_name()}
        data.setdefault("dependency_map", {})["llm"] = resolver
        for spec in data["agents"]:
            if "llm" in spec.get("dependency_map", {}):
                spec["dependency_map"]["llm"] = resolver
        builder = GuildBuilder.from_spec(GuildSpec.model_validate(data))
        builder.add_agent_spec(
            AgentBuilder(UserProxyAgent)
            .set_id("entry")
            .set_name("Entry")
            .set_description("User entry")
            .set_properties({"user_id": "reader"})
            .listen_to_default_topic(False)
            .add_additional_topic(UserProxyAgent.get_user_inbox_topic("reader"))
            .build_spec()
        )
        builder.add_agent_spec(
            AgentBuilder(ProbeAgent)
            .set_id("observer")
            .set_name("Observer")
            .set_description("Conversation output")
            .listen_to_default_topic(False)
            .add_additional_topic("user_message_broadcast")
            .add_additional_topic("error_topic")
            .add_additional_topic("system_topic")
            .build_spec()
        )
        guild = builder.bootstrap(database, "conversation-tests")
        wait_until(lambda: guild.execution_engine.agent_tracker.get_agent_wrapper(guild.id, "observer"))
        guilds.append(guild)
        wrapper = guild.execution_engine.agent_tracker.get_agent_wrapper(guild.id, "observer")
        if hasattr(wrapper, "initialization_complete"):
            assert wrapper.initialization_complete.wait(10)
        probe = wrapper.agent
        for spec in builder.build_spec().agents:
            initialized = guild.execution_engine.agent_tracker.get_agent_wrapper(guild.id, spec.id)
            if hasattr(initialized, "initialization_complete"):
                assert initialized.initialization_complete.wait(10)
                assert initialized.agent is not None
        return guild, probe, calls

    yield launch
    for guild in reversed(guilds):
        guild.shutdown()


def send(probe, text, recipients=None, raw=False):
    payload = (
        {"hello": text}
        if raw
        else ChatCompletionRequest(
            messages=[{"role": "user", "content": [{"type": "text", "text": text}]}]
        ).model_dump()
    )
    inner = Message(
        id_obj=probe._generate_id(Priority.NORMAL),
        topics="default_topic",
        sender=probe.get_agent_tag(),
        format="generic_json" if raw else get_qualified_class_name(ChatCompletionRequest),
        payload=payload,
        recipient_list=recipients or [],
    )
    probe.publish(UserProxyAgent.get_user_inbox_topic("reader"), inner)


def wait_until(predicate, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(0.01)
    pytest.fail("Catalog flow failed to complete")


def outputs(probe):
    errors = [m for m in probe.get_messages() if m.process_status == "error"]
    assert not errors, [m.payload for m in errors]
    return [m for m in probe.get_messages() if m.topic_published_to == "user_message_broadcast"]


def test_council_opinions_reviews_and_chairman_use_actual_aggregators(conversation):
    _, probe, calls = conversation("llm_council.json")
    send(probe, "How should Harbor allocate its budget?")
    wait_until(lambda: any(m.sender.id == "chairman" for m in outputs(probe)))
    roles = Counter(role for role, _ in calls)
    assert roles == {"council_member_1": 2, "council_member_2": 2, "council_member_3": 2, "chairman": 1}
    assert "How should Harbor allocate its budget?" in calls[-1][1].model_dump_json()
    for msg in outputs(probe):
        if msg.format.endswith("ChatCompletionResponse"):
            ChatCompletionResponse.model_validate(msg.payload)
    assert all(f"council_member_{i}" in calls[-1][1].model_dump_json() for i in range(1, 4))


def test_debate_routes_bounded_turns_and_fact_checks(conversation, monkeypatch):
    from rustic_ai.fact_checker.agent import FactCheckerAgent

    claims = []
    monkeypatch.delenv("GOOGLE_CLOUD_API_KEY", raising=False)

    def check(self, query):
        claims.append(query)
        return None

    monkeypatch.setattr(FactCheckerAgent, "get_claims", check)
    _, probe, calls = conversation("debate_simulator_blueprint.json")
    send(probe, "Should Harbor publish its budget?")
    wait_until(lambda: len(calls) >= 11)
    wait_until(lambda: len(claims) >= 10)
    time.sleep(0.05)
    assert len(calls) == 11
    assert Counter(role for role, _ in calls) == {"actor_1_agent": 6, "actor_2_agent": 5}
    assert len(claims) == 10
    assert any(m.format.endswith("CanvasFormat") for m in outputs(probe))
    assert "Harbor" in calls[-1][1].model_dump_json()


def test_ui_catalog_routes_all_component_messages_through_user_entry(conversation):
    _, probe, calls = conversation("ui_component_blueprint.json")
    send(probe, "Show components", raw=True)
    wait_until(lambda: len([m for m in outputs(probe) if m.sender.id != "entry"]) == 22)
    assert not calls
    assert all(m.process_status == "completed" for m in outputs(probe) if m.sender.id != "entry")
    assert len({m.format for m in outputs(probe)}) >= 18


def test_multi_model_tagging_and_dynamic_launch_keep_model_ids(conversation, monkeypatch):
    from rustic_ai.core.messaging import AgentTag
    from rustic_ai.litellm.agent_ext.llm import LiteLLMResolver

    def resolve(self, org_id, guild_id, agent_id):
        return ConversationLLM(agent_id, ConversationResolver.calls)

    monkeypatch.setattr(LiteLLMResolver, "resolve", resolve)
    guild, probe, calls = conversation("multi_llm_blueprint.json")
    data = render("multi_llm_blueprint.json")
    model_ids = [data["configuration"][key] for key in ("model_1", "model_2")]
    send(probe, "What is the Harbor budget?", recipients=[AgentTag(id=i, name=i) for i in model_ids])
    wait_until(lambda: len(calls) == 2)
    wait_until(lambda: len([m for m in outputs(probe) if m.sender.id in model_ids]) == 2)
    assert {r for r, _ in calls} == set(model_ids)
    for msg in outputs(probe):
        if msg.sender.id in model_ids:
            ChatCompletionResponse.model_validate(msg.payload)
    send(probe, "@User Input Analyser add vertex_ai/local-third")
    launch_message = wait_until(
        lambda: next((m for m in probe.get_messages() if m.format.endswith("AgentLaunchRequest")), None)
    )
    assert (
        launch_message.payload["agent_spec"]["dependency_map"]["llm"]["properties"]["model"] == "vertex_ai/local-third"
    )
    wait_until(
        lambda: any(m.format.endswith("TextFormat") and "local-third" in m.payload["text"] for m in outputs(probe))
    )
    send(probe, "Answer about Harbor", recipients=[AgentTag(id="vertex_ai/local-third", name="vertex_ai/local-third")])
    wait_until(lambda: any(r == "vertex_ai/local-third" for r, _ in calls))
    wait_until(lambda: any(m.sender.id == "vertex_ai/local-third" for m in outputs(probe)))
    assert all(
        m["role"] == "assistant"
        for m in guild.execution_engine.agent_tracker.get_agent_wrapper(guild.id, model_ids[0]).agent.get_guild_state()[
            "memories"
        ]
    )
