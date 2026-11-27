"""Exercise the shipped task and data analyst guilds with native local tools."""

import json
import time
from typing import Any, ClassVar
from uuid import uuid4

from fsspec import filesystem
from fsspec.implementations.dirfs import DirFileSystem
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


class LocalFiles(DependencyResolver[DirFileSystem]):
    root: ClassVar[str] = ""

    def resolve(self, org_id, guild_id, agent_id):
        return DirFileSystem(path=self.root, fs=filesystem("file"))


class ToolLLM(LLM):
    def __init__(self, role, calls):
        self.role, self.calls = role, calls

    @property
    def model(self):
        return "local-tool-catalog"

    def get_config(self):
        return {}

    def completion(self, prompt, model=None):
        self.calls.append((self.role, prompt))
        tools = []
        name: str | None
        args: dict[str, Any] | None
        content: str | None = "Task operation complete"
        if self.role == "task_orchestrator":
            request = prompt.messages[-1].content
            actions: dict[str, tuple[str, dict[str, Any]]] = {
                "add": (
                    "add_task",
                    {
                        "id": "harbor",
                        "todo": "Review Harbor budget",
                        "start_time": "2026-01-01T00:00:00",
                        "depends_on": [],
                    },
                ),
                "list": ("list_tasks", {"status": "all"}),
                "complete": ("update_status", {"id": "harbor", "status": "done"}),
                "delete": ("delete_task", {"id": "harbor"}),
            }
            name, args = actions[request]
            assert name in [tool.function.name for tool in prompt.tools]
            tools = [{"id": uuid4().hex, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]
        elif self.role == "react_data_analyst":
            observed = [m for m in prompt.messages if m.role == "tool"]
            if not observed:
                name, args = "load_file", {"filename": "sales.csv", "dataset_name": "sales"}
            elif len(observed) == 1:
                assert "sales" in observed[-1].content
                name, args = "query_dataset", {
                    "query_string": "SELECT SUM(amount) AS total FROM sales",
                    "input_datasets": {"sales": "sales"},
                }
            else:
                assert "42" in observed[-1].content, observed[-1].content
                name, args = None, None
                content = "Sales total is 42"
            if name:
                tools = [
                    {"id": uuid4().hex, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}
                ]
                content = None
        else:
            assert "Dataset: sales" in prompt.model_dump_json()
            content = json.dumps(
                {"table_purpose": "Harbor sales", "columns": [{"name": "amount", "description": "Sales amount"}]}
            )
        return ChatCompletionResponse(
            id=uuid4().hex,
            created=1,
            model=self.model,
            input_messages=prompt.messages,
            choices=[
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content, "tool_calls": tools or None},
                    "finish_reason": "tool_calls" if tools else "stop",
                }
            ],
        )

    async def async_completion(self, prompt, model=None):
        return self.completion(prompt, model)


class ToolResolver(DependencyResolver[LLM]):
    calls: ClassVar[list[tuple[str, ChatCompletionRequest]]] = []

    def resolve(self, org_id, guild_id, agent_id):
        return ToolLLM(agent_id, self.calls)


def until(predicate):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(0.01)
    pytest.fail("Native catalog tool flow did not complete")


@pytest.fixture
def tool_catalog(database, tmp_path):
    guilds = []

    def launch(name):
        data = load_blueprint(name)["spec"]
        data["id"] = "tool-catalog-" + uuid4().hex
        calls: list[tuple[str, ChatCompletionRequest]] = []
        ToolResolver.calls = calls
        LocalFiles.root = str(tmp_path)
        data.setdefault("dependency_map", {}).update(
            {
                "llm": {"class_name": ToolResolver.get_qualified_class_name()},
                "filesystem": {"class_name": LocalFiles.get_qualified_class_name()},
            }
        )
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
            .set_description("Tool output")
            .listen_to_default_topic(False)
            .add_additional_topic("user_message_broadcast")
            .add_additional_topic("error_topic")
            .add_additional_topic("react_data_analyst")
            .build_spec()
        )
        guild = builder.bootstrap(database, "tool-tests")
        guilds.append(guild)
        until(lambda: guild.execution_engine.agent_tracker.get_agent_wrapper(guild.id, "observer"))
        return guild, guild.execution_engine.agent_tracker.get_agent_wrapper(guild.id, "observer").agent, calls

    yield launch
    for guild in reversed(guilds):
        guild.shutdown()


def send(probe, text):
    inner = Message(
        id_obj=probe._generate_id(Priority.NORMAL),
        topics="default_topic",
        sender=probe.get_agent_tag(),
        format=get_qualified_class_name(ChatCompletionRequest),
        payload=ChatCompletionRequest(messages=[{"role": "user", "content": text}]).model_dump(),
    )
    probe.publish(UserProxyAgent.get_user_inbox_topic("reader"), inner)


def test_todo_catalog_routes_tools_and_updates_persistent_task_state(tool_catalog):
    guild, probe, calls = tool_catalog("todo_guild.json")
    agent = guild.execution_engine.agent_tracker.get_agent_wrapper(guild.id, "todo_agent").agent
    send(probe, "add")
    until(lambda: agent.get_agent_state().get("tasks"))
    assert agent.get_agent_state()["tasks"][0]["todo"] == "Review Harbor budget"
    until(lambda: any("Harbor budget" in str(m.payload) for m in probe.get_messages()))
    send(probe, "complete")
    until(lambda: agent.get_agent_state()["tasks"][0]["status"] == "done")
    until(lambda: any("marked as done" in str(m.payload) for m in probe.get_messages()))
    send(probe, "list")
    until(lambda: any("No tasks found" in str(m.payload) for m in probe.get_messages()))
    send(probe, "delete")
    until(lambda: len(calls) == 4 and not agent.get_agent_state().get("tasks"))
    assert not [m for m in probe.get_messages() if m.process_status == "error"]
    assert len(calls) == 4


def test_data_analyst_catalog_loads_queries_and_enriches_native_dataset(tool_catalog, tmp_path):
    (tmp_path / "sales.csv").write_text("item,amount\nHarbor,20\nPier,22\n")
    guild, probe, calls = tool_catalog("react_data_analyst.json")
    send(probe, "Analyze sales.csv")
    answer = until(
        lambda: next(
            (
                m
                for m in probe.get_messages()
                if m.format.endswith("ChatCompletionResponse") and m.process_status == "completed"
            ),
            None,
        )
    )
    assert answer.payload["choices"][0]["message"]["content"] == "Sales total is 42"
    inputs = [m for m in probe.get_messages() if m.format.endswith("ChatCompletionRequest")]
    assert inputs and inputs[0].session_state.get("analysis_user"), [(m.topics, m.session_state) for m in inputs]
    until(lambda: probe.get_guild_state().get("codex_enrichment", {}).get("datasets", {}).get("sales"))
    assert probe.get_guild_state()["codex_enrichment"]["datasets"]["sales"]["row_count"] == 2
    assert [role for role, _ in calls].count("react_data_analyst") == 3
    assert [role for role, _ in calls].count("codex_enrichment_llm") == 1
    assert not [m for m in probe.get_messages() if m.process_status == "error"]
