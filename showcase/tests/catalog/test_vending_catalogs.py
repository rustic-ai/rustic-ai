"""Run the authored VendingBench and player guilds across their real G2G boundary."""

import json
import time
from types import SimpleNamespace
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
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder, GuildHelper
from rustic_ai.core.guild.dsl import GuildSpec
from rustic_ai.core.messaging import Message, Priority
from rustic_ai.showcase.catalog import load_blueprint
from rustic_ai.showcase.vending_bench.config import ProductType


class PlayerLLM(LLM):
    def __init__(self, calls, actions):
        self.calls, self.actions = calls, actions

    @property
    def model(self):
        return "local-vending"

    def get_config(self):
        return {}

    def completion(self, prompt, model=None):
        self.calls.append(prompt)
        if len(self.calls) > 12:
            raise RuntimeError("Player exceeded bounded action loop")
        if self.actions:
            tool, arguments = self.actions.pop(0)
            message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": uuid4().hex,
                        "type": "function",
                        "function": {"name": tool, "arguments": json.dumps(arguments)},
                    }
                ],
            }
            finish = "tool_calls"
        else:
            message, finish = {"role": "assistant", "content": "Completed vending audit"}, "stop"
        return ChatCompletionResponse(
            id=uuid4().hex,
            created=1,
            model=self.model,
            choices=[{"index": 0, "message": message, "finish_reason": finish}],
        )

    async def async_completion(self, prompt, model=None):
        return self.completion(prompt, model)


class PlayerResolver(DependencyResolver[LLM]):
    calls: list[ChatCompletionRequest] = []
    actions: list[tuple[str, dict]] = []

    def resolve(self, org_id, guild_id, agent_id):
        return PlayerLLM(self.calls, self.actions)


def wait_for(predicate, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if value := predicate():
            return value
        time.sleep(0.01)
    pytest.fail("Paired vending catalog did not complete")


def observer(builder, id):
    builder.add_agent_spec(
        AgentBuilder(ProbeAgent)
        .set_id(id)
        .set_name(id)
        .set_description("Observe catalog messages")
        .listen_to_default_topic(False)
        .add_additional_topic("default_topic")
        .add_additional_topic("user_message_broadcast")
        .add_additional_topic("error_topic")
        .add_additional_topic("PLAYER_INPUT")
        .add_additional_topic("SIMULATION_CONTROL")
        .build_spec()
    )


def instance(guild, id):
    wrapper = guild.execution_engine.agent_tracker.get_agent_wrapper(guild.id, id)
    if hasattr(wrapper, "initialization_complete"):
        assert wrapper.initialization_complete.wait(30)
    return wrapper.agent


@pytest.fixture
def pair(monkeypatch, database):
    import rustic_ai.vertexai.client as vertex_client

    research = []

    class LocalResearch:
        def generate_content(self, **kwargs):
            research.append(kwargs)
            return SimpleNamespace(
                text="Harbor Wholesale, orders@harbor.example, local supplier of chips and soda.", candidates=[]
            )

    monkeypatch.setattr(vertex_client.genai, "Client", lambda **kwargs: SimpleNamespace(models=LocalResearch()))
    guilds = []

    def launch(actions, threaded=False):
        bench = load_blueprint("vending_bench_guild.json")["spec"]
        bench["id"] = "vending-" + uuid4().hex
        calls: list[ChatCompletionRequest] = []
        PlayerResolver.calls, PlayerResolver.actions = calls, list(actions)
        resolver = {"class_name": PlayerResolver.get_qualified_class_name()}
        bench["dependency_map"]["llm"] = resolver
        bench_builder = GuildBuilder.from_spec(GuildSpec.model_validate(bench))
        if threaded:
            bench_builder.set_execution_engine(
                "rustic_ai.core.guild.execution.multithreaded.multithreaded_exec_engine.MultiThreadedEngine"
            )
        observer(bench_builder, "bench_observer")
        server = bench_builder.bootstrap(database, "vending-catalog-tests")
        wait_for(
            lambda: server.execution_engine.agent_tracker.get_agent_wrapper(server.id, "bench_observer"), timeout=30
        )
        guilds.append(server)
        instance(server, GuildHelper.get_manager_agent_id(server.id))
        for spec in bench["agents"]:
            instance(server, spec["id"])
        player = load_blueprint("vending_bench_player_guild.json")["spec"]
        player["id"] = "player-" + uuid4().hex
        player["dependency_map"]["llm"] = resolver
        for spec in player["agents"]:
            if spec["id"] == "envoy_to_vending_bench":
                spec["properties"]["target_guild"] = server.id
        player_builder = GuildBuilder.from_spec(GuildSpec.model_validate(player))
        if threaded:
            player_builder.set_execution_engine(
                "rustic_ai.core.guild.execution.multithreaded.multithreaded_exec_engine.MultiThreadedEngine"
            )
        observer(player_builder, "player_observer")
        player_builder.add_agent_spec(
            AgentBuilder(UserProxyAgent)
            .set_id("entry")
            .set_name("Entry")
            .set_description("User entry")
            .set_properties({"user_id": "operator"})
            .listen_to_default_topic(False)
            .add_additional_topic(UserProxyAgent.get_user_inbox_topic("operator"))
            .build_spec()
        )
        client = player_builder.bootstrap(database, "vending-catalog-tests")
        wait_for(
            lambda: client.execution_engine.agent_tracker.get_agent_wrapper(client.id, "player_observer"), timeout=30
        )
        guilds.append(client)
        instance(client, GuildHelper.get_manager_agent_id(client.id))
        for spec in player["agents"]:
            instance(client, spec["id"])
        instance(client, "entry")
        return server, client, instance(client, "player_observer"), calls, research

    yield launch
    for guild in reversed(guilds):
        guild.shutdown()


def send_player(probe):
    request = ChatCompletionRequest(
        messages=[{"role": "user", "content": "Audit inventory, update prices and record notes"}]
    )
    message = Message(
        id_obj=probe._generate_id(Priority.NORMAL),
        topics="default_topic",
        sender=probe.get_agent_tag(),
        format="rustic_ai.core.guild.agent_ext.depends.llm.models.ChatCompletionRequest",
        payload=request.model_dump(),
    )
    probe.publish(UserProxyAgent.get_user_inbox_topic("operator"), message)


def completed(probe):
    messages = [m for m in probe.get_messages() if m.process_status == "completed" and m.sender.id == "player_agent"]
    return messages


def test_paired_catalog_tools_update_machine_and_roundtrip_supplier_scratchpad(pair):
    actions = [
        ("check_inventory", {}),
        ("set_price", {"product": "chips", "new_price": 3.5}),
        ("scratchpad_write", {"key": "audit", "value": "HARBOR_AUDIT_NOTE"}),
        ("scratchpad_read", {"key": "audit"}),
        ("check_balance", {}),
    ]
    server, client, probe, calls, _ = pair(actions)
    send_player(probe)
    final = wait_for(lambda: completed(probe))
    assert len(final) == 1 and "Completed vending audit" in json.dumps(final[0].payload)
    assert len(calls) == len(actions) + 1
    assert instance(server, "vending_machine").prices[ProductType.CHIPS] == 3.5
    assert "HARBOR_AUDIT_NOTE" in calls[-2].model_dump_json(), [
        [m.content for m in c.messages if m.role == "user"] for c in calls
    ]
    received = [
        m for m in instance(server, "bench_observer").get_messages() if m.format.endswith("AgentActionResponse")
    ]
    assert [m.payload["action_type"] for m in received] == [name for name, _ in actions]
    assert all(m.payload["success"] for m in received)
    assert len({m.payload["request_id"] for m in received}) == len(actions)
    assert not [m for m in probe.get_messages() if m.process_status == "error"]
    assert instance(client, "envoy_to_vending_bench").config.target_guild == server.id


@pytest.mark.parametrize("threaded", [False, True])
def test_paired_catalog_supplier_research_reaches_registry_and_player(pair, threaded):
    server, _, probe, calls, research = pair([("search_suppliers", {}), ("view_suppliers", {})], threaded=threaded)
    send_player(probe)
    assert len(wait_for(lambda: completed(probe))) == 1
    assert len(calls) == 3 and len(research) == 1
    assert "Harbor" in calls[-1].model_dump_json() and "orders@harbor.example" in calls[-1].model_dump_json()
    discovery = instance(server, "supplier_discovery")
    assert discovery.registry.suppliers and not discovery._pending_completions and not discovery.pending_searches
    assert not discovery.get_guild_state().get("pending_supplier_searches")
    assert not [m for m in probe.get_messages() if m.process_status == "error"]


@pytest.mark.parametrize("threaded", [False, True])
def test_registry_owner_read_ignores_delayed_consumer_snapshots(pair, monkeypatch, threaded):
    from rustic_ai.showcase.vending_bench.supplier_agent import SupplierAgent
    from rustic_ai.showcase.vending_bench.supplier_registry import SupplierRegistry

    delayed = []
    original = SupplierAgent.on_state_updated

    def delay_registry_snapshot(agent, state, ctx):
        original(agent, state, ctx)
        if state.get("supplier_registry", {}).get("suppliers"):
            delayed.append(ctx.payload.version)
            # Simulate this consumer receiving the owner's registry snapshot later.
            # The actual owner and all other agents still receive the real update.
            agent._guild_state = {**state, "supplier_registry": SupplierRegistry().model_dump()}
            agent.registry = SupplierRegistry()

    monkeypatch.setattr(SupplierAgent, "on_state_updated", delay_registry_snapshot)
    server, _, probe, calls, research = pair([("search_suppliers", {}), ("view_suppliers", {})], threaded=threaded)
    send_player(probe)
    assert len(wait_for(lambda: completed(probe))) == 1
    wait_for(lambda: delayed)
    consumer = instance(server, "supplier")
    assert not consumer.registry.suppliers and not consumer.get_guild_state()["supplier_registry"]["suppliers"]
    assert len(calls) == 3 and len(research) == 1 and "orders@harbor.example" in calls[-1].model_dump_json()
    views = [
        message
        for message in instance(server, "bench_observer").get_messages()
        if message.format.endswith("ViewSuppliersResponse")
    ]
    assert len(views) == 1 and views[0].sender.id == "supplier_discovery"
    assert views[0].payload["suppliers"] and len(completed(probe)) == 1
    assert not [message for message in probe.get_messages() if message.is_error_message]
