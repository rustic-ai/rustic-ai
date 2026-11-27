"""Tool schemas, actual provider IDs, and typed observation adapters."""

import json
from pathlib import Path
import time

import pytest

from rustic_ai.core.agents.testutils.probe_agent import ProbeAgent
from rustic_ai.core.guild.agent_ext.depends import DependencyResolver
from rustic_ai.core.guild.agent_ext.depends.llm.llm import LLM
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    AssistantMessage,
    ChatCompletionRequest,
    ChatCompletionResponse,
    Choice,
    ToolMessage,
    UserMessage,
)
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.guild.dsl import AgentSpec, GuildSpec
from rustic_ai.unidb.tools import NAMED_OPERATIONS, PR_OPERATIONS, QueryArguments


class ScriptedLLM(LLM):
    prompts: list[ChatCompletionRequest] = []

    def completion(self, prompt, model=None):
        self.prompts.append(prompt)
        if len(self.prompts) == 1:
            message = AssistantMessage(
                tool_calls=[
                    {"id": "actual-call-id", "type": "function", "function": {"name": "list_labels", "arguments": "{}"}}
                ]
            )
            finish = "tool_calls"
        else:
            assert isinstance(prompt.messages[-1], ToolMessage)
            assert prompt.messages[-1].tool_call_id == "actual-call-id"
            assert json.loads(prompt.messages[-1].content)["result"]["labels"] == []
            message = AssistantMessage(content="Database inspected.")
            finish = "stop"
        return ChatCompletionResponse(
            id="fake", created=0, model="fake", choices=[Choice(index=0, message=message, finish_reason=finish)]
        )

    async def async_completion(self, prompt, model=None):
        return self.completion(prompt, model)

    @property
    def model(self):
        return "fake"

    def get_config(self):
        return {}


class MultiStepLLM(ScriptedLLM):
    def completion(self, prompt, model=None):
        if len(self.prompts) == 1:
            self.prompts.append(prompt)
            message = AssistantMessage(
                tool_calls=[
                    {"id": "second-call-id", "type": "function", "function": {"name": "get_schema", "arguments": "{}"}}
                ]
            )
            return ChatCompletionResponse(
                id="second",
                created=0,
                model="fake",
                choices=[Choice(index=0, message=message, finish_reason="tool_calls")],
            )
        if len(self.prompts) == 2:
            self.prompts.append(prompt)
            observations = [m for m in prompt.messages if isinstance(m, ToolMessage)]
            assert [m.tool_call_id for m in observations] == ["actual-call-id", "second-call-id"]
            assert json.loads(observations[0].content)["result"]["labels"] == []
            return ChatCompletionResponse(
                id="final",
                created=0,
                model="fake",
                choices=[
                    Choice(index=0, message=AssistantMessage(content="Database inspected."), finish_reason="stop")
                ],
            )
        return super().completion(prompt, model)


class ReconcileLLM(ScriptedLLM):
    def completion(self, prompt, model=None):
        self.prompts.append(prompt)
        assert len(self.prompts) == 1, "Unknown writes must not continue the model loop"
        message = AssistantMessage(
            tool_calls=[
                {
                    "id": "write-call-id",
                    "type": "function",
                    "function": {"name": "create_label", "arguments": '{"label":"Interrupted"}'},
                }
            ]
        )
        return ChatCompletionResponse(
            id="write", created=0, model="fake", choices=[Choice(index=0, message=message, finish_reason="tool_calls")]
        )


class DiagnosticPlanLLM(ScriptedLLM):
    family = "DBQueryPlan"
    tool = "query_plan"

    def completion(self, prompt, model=None):
        self.prompts.append(prompt)
        if len(self.prompts) == 1:
            message = AssistantMessage(
                tool_calls=[
                    {
                        "id": "diagnostic-call",
                        "type": "function",
                        "function": {"name": self.tool, "arguments": '{"operation":"constant","params":{"value":1}}'},
                    }
                ]
            )
            finish = "tool_calls"
        else:
            observation = prompt.messages[-1]
            assert isinstance(observation, ToolMessage)
            assert observation.tool_call_id == "diagnostic-call"
            result = json.loads(observation.content)["result"]
            assert result["executed"] == (self.family == "DBQueryProfile")
            if result["executed"]:
                assert result["query"]["rows"] == [{"value": 1}]
            else:
                assert not result["planning_timeout_enforced"]
            message = AssistantMessage(content="Database inspected.")
            finish = "stop"
        return ChatCompletionResponse(
            id="diagnostic", created=0, model="fake", choices=[Choice(index=0, message=message, finish_reason=finish)]
        )


class DiagnosticProfileLLM(DiagnosticPlanLLM):
    family = "DBQueryProfile"
    tool = "query_profile"


class ScriptedResolver(DependencyResolver[LLM]):
    llm_class = ScriptedLLM

    def resolve(self, org_id, guild_id, agent_id):
        return self.llm_class()


def test_tool_schemas_hide_framework_identifiers():
    from rustic_ai.unidb import tools

    for name in PR_OPERATIONS + NAMED_OPERATIONS:
        schema = getattr(tools, name + "Arguments").model_json_schema()
        assert not set(schema["properties"]) & {
            "request_id",
            "operation_id",
            "correlation_id",
            "tool_call_id",
            "tool_name",
        }
        assert schema["additionalProperties"] is False
    with pytest.raises(ValueError):
        QueryArguments(query="RETURN 1", principal="administrator")


@pytest.mark.parametrize(
    "llm_class,turns",
    [(ScriptedLLM, 2), (MultiStepLLM, 3), (ReconcileLLM, 1), (DiagnosticPlanLLM, 2), (DiagnosticProfileLLM, 2)],
)
def test_complete_showcase_tool_loop_with_deterministic_llm(tmp_path, llm_class, turns, monkeypatch):
    path = Path(__file__).resolve().parents[2] / "showcase/apps/unidb_assistant.json"
    spec = json.loads(path.read_text())["spec"]
    spec["dependency_map"]["filesystem"]["properties"]["path_base"] = str(tmp_path)
    spec["dependency_map"]["llm"] = {"class_name": __name__ + ".ScriptedResolver", "properties": {}}
    if issubclass(llm_class, DiagnosticPlanLLM):
        spec["agents"][1]["properties"]["operation_catalog"] = {
            "operations": [
                {
                    "name": "constant",
                    "kind": "query",
                    "query": "RETURN $value AS value",
                    "columns": ["value"],
                    "parameters_schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["value"],
                        "properties": {"value": {"type": "integer"}},
                    },
                }
            ]
        }
        spec["agents"][0]["properties"]["llm_request_wrappers"][0]["toolset"]["tools"].append(
            {
                "name": llm_class.tool,
                "description": "Inspect a named query",
                "parameter_class": "rustic_ai.unidb.tools." + llm_class.family + "Arguments",
            }
        )
        for producer, format, topic in [
            ("query-processor", "rustic_ai.unidb.tools." + llm_class.family + "Arguments", "unidb.tool.requests"),
            ("unidb-tool-adapter", "rustic_ai.unidb.models." + llm_class.family + "Request", "unidb"),
            ("unidb", "rustic_ai.unidb.models." + llm_class.family + "Response", "unidb.observations"),
        ]:
            spec["routes"]["steps"].append(
                {
                    "agent": {"id": producer},
                    "message_format": format,
                    "destination": {"topics": topic},
                    "route_times": -1,
                }
            )
    agents = [AgentSpec.model_validate(a, context={"require_agent_class": True}) for a in spec["agents"]]
    spec["agents"] = []
    guild = GuildBuilder.from_spec(GuildSpec.model_validate(spec)).launch("demo")
    ScriptedResolver.llm_class = llm_class
    llm_class.prompts = []
    if llm_class is ReconcileLLM:
        from rustic_ai.unidb.runtime import UniDBRuntime

        original = UniDBRuntime._admin

        def interrupted(runtime, request):
            original(runtime, request)
            raise RuntimeError("Injected reporting failure after native schema application")

        monkeypatch.setattr(UniDBRuntime, "_admin", interrupted)
    launched = []
    try:
        for agent in agents:
            launched.append(guild._add_local_agent(agent))
        probe = guild._add_local_agent(
            AgentBuilder(ProbeAgent)
            .set_id("user")
            .set_name("User")
            .set_description("test user")
            .add_additional_topic("user_message_broadcast")
            .listen_to_default_topic(False)
            .build_spec()
        )
        probe.publish_with_guild_route(
            "query_processor", ChatCompletionRequest(messages=[UserMessage(content="Inspect the database")])
        )
        deadline = time.monotonic() + 5
        while not probe.get_messages() and time.monotonic() < deadline:
            time.sleep(0.01)
        messages = probe.get_messages()
        assert len(messages) == 1
        if llm_class is ReconcileLLM:
            assert messages[0].payload["text"].startswith("Database operation requires reconciliation.")
            assert '"effect":"unknown"' in messages[0].payload["text"]
        else:
            assert messages[0].payload["text"] == "Database inspected."
        assert len(llm_class.prompts) == turns
    finally:
        for agent in launched:
            if "unidb" in agent._dependency_resolvers:
                agent._dependency_resolvers["unidb"].close()
        guild.shutdown()
