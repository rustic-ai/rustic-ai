"""Composed native diagnostics workflow and correlated terminal routing."""

import json
from pathlib import Path
import time

import pytest
from rustic_ai.showcase.unidb_query_diagnostics import RunIndexComparison

from rustic_ai.core.agents.testutils.probe_agent import ProbeAgent
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.guild.dsl import AgentSpec, GuildSpec
from rustic_ai.unidb import models as m
from rustic_ai.unidb.runtime import RuntimeFailure, UniDBRuntime

APP = Path(__file__).resolve().parents[2] / "apps/unidb_query_diagnostics.json"


def launch():
    raw = json.loads(APP.read_text())["spec"]
    agents = [AgentSpec.model_validate(a, context={"require_agent_class": True}) for a in raw["agents"]]
    raw["agents"] = []
    guild = GuildBuilder.from_spec(GuildSpec.model_validate(raw)).launch("test-org")
    database = guild._add_local_agent(agents[0])
    driver = guild._add_local_agent(agents[1])
    probe = guild._add_local_agent(
        AgentBuilder(ProbeAgent)
        .set_id("caller")
        .set_name("Caller")
        .set_description("Diagnostics caller")
        .add_additional_topic("diagnostics.results")
        .add_additional_topic("user_message_broadcast")
        .listen_to_default_topic(False)
        .build_spec()
    )
    return guild, database, driver, probe


def wait_result(probe):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        results = [msg for msg in probe.get_messages() if msg.topic_published_to == "diagnostics.results"]
        if results:
            return results[0]
        time.sleep(0.01)
    pytest.fail("No diagnostics terminal result")


@pytest.mark.parametrize("fail", [False, True])
def test_composed_native_comparison_and_failure(fail, monkeypatch):
    if fail:

        def failure(*args):
            raise RuntimeFailure("native_error", "plan", "injected plan failure")

        monkeypatch.setattr(UniDBRuntime, "_diagnostic", failure)
    guild, database, driver, probe = launch()
    req = RunIndexComparison(request_id="comparison", correlation_id="workflow")
    try:
        unexpected = m.DBQueryPlanResponse(
            request_id="unexpected", correlation_id=req.correlation_id, binding_id="diagnostics", result={}
        )
        probe.publish_with_guild_route("diagnostics.observations", unexpected)
        assert driver._run is None
        probe.publish_with_guild_route("diagnostics.start", req)
        result = wait_result(probe)
        assert result.payload["request_id"] == req.request_id
        assert result.payload["correlation_id"] == req.correlation_id
        if fail:
            assert result.process_status == "error"
            assert result.payload["outcome"] == "failed"
            assert result.payload["comparison"]["failure"]["error"]["effect"] == "not_started"
            assert driver._run["stage"] == 2
        else:
            assert result.process_status == "completed"
            before, after = (result.payload["comparison"][k] for k in ("before", "after"))
            assert before["profile"]["rows"] == after["profile"]["rows"] == [{"name": "widget:12"}]
            assert before["profile"]["query_metrics"]["rows_scanned"] == 50
            assert after["profile"]["query_metrics"]["rows_scanned"] == 1
            assert after["plan"]["index_usage"][0]["used"]
        probe.publish_with_guild_route("diagnostics.start", req)
        probe.publish_with_guild_route("diagnostics.observations", unexpected)
        time.sleep(0.05)
        assert len([msg for msg in probe.get_messages() if msg.topic_published_to == "diagnostics.results"]) == 1
        presentation = [msg for msg in probe.get_messages() if msg.topic_published_to == "user_message_broadcast"]
        assert len(presentation) == 1
        assert json.loads(presentation[0].payload["text"]) == result.payload
    finally:
        database._dependency_resolvers["unidb"].close()
        guild.shutdown()
