"""Execute every Iterative Studio mode using the shipped routes and local models."""

from dataclasses import dataclass, field
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


@dataclass
class Script:
    mode: str
    bounded_retry: bool = False
    calls: list = field(default_factory=list)


class LocalPipelineLLM(LLM):
    def __init__(self, script, role):
        self.script, self.role = script, role

    @property
    def model(self):
        return "local-pipeline-test"

    def get_config(self):
        return {}

    def completion(self, prompt, model=None):
        self.script.calls.append((self.role, prompt))
        if len(self.script.calls) > 40:
            raise RuntimeError("Pipeline failed to terminate within its declared bounds")
        if self.role == "mode_controller":
            content = self.script.mode
        elif self.role == "critique_agent":
            content = "NEEDS_REVISION" if self.script.bounded_retry else "APPROVE"
        elif self.role == "ctx_iterative":
            content = "Revise the draft" if self.script.bounded_retry else "APPROVE"
        else:
            content = "Harbor final result from " + str(self.role)
        return ChatCompletionResponse(
            id=uuid4().hex,
            created=1,
            model=self.model,
            input_messages=prompt.messages,
            choices=[{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        )

    async def async_completion(self, prompt, model=None):
        return self.completion(prompt, model)


class PipelineResolver(DependencyResolver[LLM]):
    script: Script | None = None

    def resolve(self, org_id, guild_id, agent_id):
        assert self.script is not None
        return LocalPipelineLLM(self.script, agent_id)


@pytest.fixture
def pipeline(tmp_path, database):
    guilds = []

    def launch(mode, bounded_retry=False):
        script = Script(mode, bounded_retry)
        PipelineResolver.script = script
        data = load_blueprint("iterative_studio/iterative_studio.json")["spec"]
        data["id"] = "iterative-" + uuid4().hex
        data["dependency_map"]["llm"] = {"class_name": PipelineResolver.get_qualified_class_name()}
        data["dependency_map"]["filesystem"]["properties"]["path_base"] = str(tmp_path)
        builder = GuildBuilder.from_spec(GuildSpec.model_validate(data))
        observer = (
            AgentBuilder(ProbeAgent)
            .set_id("caller")
            .set_name("Caller")
            .set_description("Pipeline observer")
            .add_additional_topic("user_message_broadcast")
            .listen_to_default_topic(False)
            .build_spec()
        )
        builder.add_agent_spec(observer)
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
        guild = builder.bootstrap(database, "pipeline-tests")
        deadline = time.monotonic() + 10
        while not guild.execution_engine.agent_tracker.get_agent_wrapper(guild.id, "caller"):
            assert time.monotonic() < deadline
            time.sleep(0.01)
        guilds.append(guild)
        probe = guild.execution_engine.agent_tracker.get_agent_wrapper(guild.id, "caller").agent
        return guild, probe, script

    yield launch
    for guild in guilds:
        guild.shutdown()


def run_turn(probe, text="Original Harbor request"):
    inner = Message(
        id_obj=probe._generate_id(Priority.NORMAL),
        topics="default_topic",
        sender=probe.get_agent_tag(),
        format=get_qualified_class_name(ChatCompletionRequest),
        payload=ChatCompletionRequest(messages=[{"role": "user", "content": text}]).model_dump(),
    )
    probe.publish(UserProxyAgent.get_user_inbox_topic("reader"), inner)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        messages = [m for m in probe.get_messages() if m.format.endswith("ChatCompletionResponse")]
        if messages:
            assert len(messages) == 1
            assert messages[0].process_status == "completed"
            assert messages[0].format.endswith("ChatCompletionResponse")
            return messages[0]
        time.sleep(0.01)
    script = PipelineResolver.script
    assert script is not None
    pytest.fail(
        "No terminal pipeline answer; calls="
        + str([(role, prompt.messages[-1].content) for role, prompt in script.calls])
    )


@pytest.mark.parametrize(
    "mode,roles",
    [
        ("refine", ["mode_controller", "feature_novelty", "feature_quality", "bug_fixer"]),
        (
            "deepthink",
            ["mode_controller", "strategy_gen", "solution_agent", "critique_agent", "red_team", "final_judge"],
        ),
        ("adaptive", ["mode_controller", "adaptive_dt"]),
        ("agentic", ["mode_controller", "agentic_agent"]),
        ("contextual", ["mode_controller", "ctx_main", "ctx_iterative", "ctx_memory"]),
    ],
)
def test_each_mode_runs_its_actual_pipeline_and_emits_one_answer(pipeline, mode, roles):
    guild, probe, script = pipeline(mode)
    result = run_turn(probe)
    observed = [role for role, _ in script.calls]
    if mode == "refine":
        assert observed[0] == roles[0] and observed[-1] == roles[-1]
        assert sorted(observed[1:-1]) == sorted(roles[1:-1])
    else:
        assert observed == roles
    assert "Harbor final result" in result.payload["choices"][0]["message"]["content"]
    assert "Original Harbor request" in script.calls[1][1].model_dump_json()
    time.sleep(0.03)
    assert len([m for m in probe.get_messages() if m.format.endswith("ChatCompletionResponse")]) == 1


@pytest.mark.parametrize("mode", ["deepthink", "contextual"])
def test_revision_loops_stop_at_declared_bounds(pipeline, mode):
    _, probe, script = pipeline(mode, bounded_retry=True)
    run_turn(probe)
    roles = [role for role, _ in script.calls]
    if mode == "deepthink":
        assert roles.count("refinement_agent") == 2
        assert roles.count("critique_agent") == 3
        assert roles[-1] == "final_judge"
    else:
        assert roles.count("ctx_main") == roles.count("ctx_iterative") == 5
        assert roles[-1] == "ctx_memory"


def test_refine_aggregation_is_isolated_between_requests(pipeline):
    _, probe, script = pipeline("refine")
    run_turn(probe, "First Harbor request")
    probe.clear_messages()
    run_turn(probe, "Second Pier request")
    assert len(script.calls) == 8
    assert "Second Pier request" in script.calls[5][1].model_dump_json()


def test_unknown_mode_falls_back_to_contextual_pipeline(pipeline):
    _, probe, script = pipeline("unknown")
    run_turn(probe)
    assert [role for role, _ in script.calls] == ["mode_controller", "ctx_main", "ctx_iterative", "ctx_memory"]
