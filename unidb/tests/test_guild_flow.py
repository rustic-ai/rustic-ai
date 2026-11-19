"""Actual messaging delivery through native UniDB processors and guild routes."""

import json
from pathlib import Path
import time

import pytest

from rustic_ai.core.agents.testutils.probe_agent import ProbeAgent
from rustic_ai.core.guild.agent import Agent, ProcessContext, processor
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.guild.dsl import AgentSpec, GuildSpec, GuildTopics
from rustic_ai.unidb import models as m

EXAMPLES = Path(__file__).resolve().parents[2] / "docs/design/uni-db-agent-examples"


def wait_for(probe, request_id, count=1):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        matches = [msg for msg in probe.get_messages() if msg.payload.get("request_id") == request_id]
        if len(matches) >= count:
            return matches
        time.sleep(0.01)
    pytest.fail("No correlated result for " + request_id)


def test_native_guild_routing_duplicate_and_error(tmp_path):
    raw = json.loads((EXAMPLES / "supply-network-init.json").read_text())
    raw["dependency_map"]["filesystem"]["properties"]["path_base"] = str(tmp_path)
    agent_spec = AgentSpec.model_validate(raw["agents"][0], context={"require_agent_class": True})
    raw["agents"] = []
    guild = GuildBuilder.from_spec(GuildSpec.model_validate(raw)).launch("test-org")
    database = guild._add_local_agent(agent_spec)
    probe = guild._add_local_agent(
        AgentBuilder(ProbeAgent)
        .set_id("demo-ingester")
        .set_name("demo-ingester")
        .set_description("Test caller")
        .add_additional_topic("db.results")
        .add_additional_topic(GuildTopics.ERROR_TOPIC)
        .listen_to_default_topic(False)
        .build_spec()
    )
    resolver = database._dependency_resolvers["unidb"]
    try:
        fixture = json.loads((EXAMPLES / "supply-network-messages.json").read_text())["exchanges"]
        request = m.DBMutateRequest.model_validate(fixture[0]["request"]["payload"])
        probe.publish_with_guild_route("db.requests", request)
        (first,) = wait_for(probe, request.request_id)
        assert first.topic_published_to == "db.results"
        assert first.payload["result"]["statistics"]["nodes_created"] == 3
        replay = request.model_copy(update={"request_id": "retry"})
        probe.publish_with_guild_route("db.requests", replay)
        assert wait_for(probe, "retry")[0].payload["result"]["replayed"]
        invalid = m.DBMutateRequest.model_validate(fixture[3]["request"]["payload"])
        probe.publish_with_guild_route("db.requests", invalid)
        (failure,) = wait_for(probe, invalid.request_id)
        assert failure.topic_published_to == GuildTopics.ERROR_TOPIC
        assert failure.format.endswith(".DBFailure")
        assert failure.payload["error"]["code"] == "operation_id_conflict"
        assert failure.process_status == first.process_status  # Error publication does not decide workflow termination.
        # Default-topic filtering excludes unrelated requests.
        probe.publish_with_guild_route("default_topic", request.model_copy(update={"request_id": "ignored"}))
        time.sleep(0.05)
        assert not [msg for msg in probe.get_messages() if msg.payload.get("request_id") == "ignored"]
    finally:
        resolver.close()  # General guild/resource shutdown hook remains deferred.
        guild.shutdown()


def test_publication_failure_recovers_without_competing_failure(tmp_path, monkeypatch):
    from rustic_ai.core.guild.agent import ProcessContext

    raw = json.loads((EXAMPLES / "supply-network-init.json").read_text())
    raw["dependency_map"]["filesystem"]["properties"]["path_base"] = str(tmp_path)
    native = AgentSpec.model_validate(raw["agents"][0], context={"require_agent_class": True})
    raw["agents"] = []
    guild = GuildBuilder.from_spec(GuildSpec.model_validate(raw)).launch("org")
    db = guild._add_local_agent(native)
    probe = guild._add_local_agent(
        AgentBuilder(ProbeAgent)
        .set_id("caller")
        .set_name("Caller")
        .set_description("caller")
        .add_additional_topic("db.results")
        .add_additional_topic(GuildTopics.ERROR_TOPIC)
        .listen_to_default_topic(False)
        .build_spec()
    )
    original_send = ProcessContext.send
    failed = [False]

    def fail_once(ctx, payload, *args, **kwargs):
        if isinstance(payload, m.DBMutateResponse) and not failed[0]:
            failed[0] = True
            raise RuntimeError("injected publication failure")
        return original_send(ctx, payload, *args, **kwargs)

    monkeypatch.setattr(ProcessContext, "send", fail_once)
    request = m.DBMutateRequest.model_validate(
        json.loads((EXAMPLES / "supply-network-messages.json").read_text())["exchanges"][0]["request"]["payload"]
    )
    try:
        probe.publish_with_guild_route("db.requests", request)
        deadline = time.monotonic() + 5
        while not failed[0] and time.monotonic() < deadline:
            time.sleep(0.01)
        assert failed[0]
        assert not [msg for msg in probe.get_messages() if msg.format.endswith(".DBFailure")]
        probe.publish_with_guild_route("db.requests", request.model_copy(update={"request_id": "publication-retry"}))
        assert wait_for(probe, "publication-retry")[0].payload["result"]["replayed"]
    finally:
        db._dependency_resolvers["unidb"].close()
        guild.shutdown()


class ExampleAccessBoundary(Agent):
    """Illustrative guild policy for the fixture, not production authentication."""

    @processor(m.DBMutateRequest)
    def authorize_write(self, ctx: ProcessContext):
        if ctx.message.sender.id != "demo-approved-executor":
            ctx.send_error(
                m.DBFailure(
                    request_id=ctx.payload.request_id,
                    correlation_id=ctx.payload.correlation_id,
                    binding_id="supplier-network",
                    error=m.ErrorDetail(
                        code="capability_denied",
                        stage="guild_access",
                        effect="not_started",
                        message="Guild caller profile cannot invoke mutations",
                    ),
                )
            )
            return
        ctx.send(ctx.payload, on_topic="db.requests")


def test_guild_owned_denial_prevents_database_dispatch(tmp_path):
    raw = json.loads((EXAMPLES / "supplier-scenario-init.json").read_text())
    raw["dependency_map"]["filesystem"]["properties"]["path_base"] = str(tmp_path)
    native = AgentSpec.model_validate(raw["agents"][0], context={"require_agent_class": True})
    raw["agents"] = []
    guild = GuildBuilder.from_spec(GuildSpec.model_validate(raw)).launch("org")
    database = guild._add_local_agent(native)
    guild._add_local_agent(
        AgentBuilder(ExampleAccessBoundary)
        .set_id("demo-access-boundary")
        .set_name("Example access boundary")
        .set_description("Guild-owned policy demonstration")
        .add_additional_topic("db.access.requests")
        .listen_to_default_topic(False)
        .build_spec()
    )
    probe = guild._add_local_agent(
        AgentBuilder(ProbeAgent)
        .set_id("demo-reasoner")
        .set_name("Reasoner")
        .set_description("Unauthorized mutation caller")
        .add_additional_topic(GuildTopics.ERROR_TOPIC)
        .listen_to_default_topic(False)
        .build_spec()
    )
    fixture = next(
        e
        for e in json.loads((EXAMPLES / "supplier-scenario-messages.json").read_text())["exchanges"]
        if e["step_id"] == "reasoner-write-refused"
    )
    req = m.DBMutateRequest.model_validate(fixture["request"]["payload"])
    resolver = database._dependency_resolvers["unidb"]
    try:
        probe.publish_with_guild_route("db.access.requests", req)
        failure = wait_for(probe, req.request_id)[0]
        assert failure.sender.id == "demo-access-boundary"
        assert failure.payload["error"]["code"] == "capability_denied"
        runtime = resolver.get_or_resolve("org", guild.id, database.id)
        assert (
            runtime.execute(
                m.DBOperationStatusRequest(request_id="status", correlation_id="test", operation_id=req.operation_id),
                "demo-access-boundary",
            )["state"]
            == "unseen"
        )
    finally:
        resolver.close()
        guild.shutdown()


def test_full_response_limit_preserves_committed_effect(tmp_path):
    raw = json.loads((EXAMPLES / "supply-network-init.json").read_text())
    raw["dependency_map"]["filesystem"]["properties"]["path_base"] = str(tmp_path)
    native = AgentSpec.model_validate(raw["agents"][0], context={"require_agent_class": True})
    raw["agents"] = []
    guild = GuildBuilder.from_spec(GuildSpec.model_validate(raw)).launch("org")
    database = guild._add_local_agent(native)
    probe = guild._add_local_agent(
        AgentBuilder(ProbeAgent)
        .set_id("caller")
        .set_name("Caller")
        .set_description("Bounded response caller")
        .add_additional_topic("db.results")
        .add_additional_topic(GuildTopics.ERROR_TOPIC)
        .listen_to_default_topic(False)
        .build_spec()
    )
    original = m.DBMutateRequest.model_validate(
        json.loads((EXAMPLES / "supply-network-messages.json").read_text())["exchanges"][0]["request"]["payload"]
    )
    try:
        probe.publish_with_guild_route("db.requests", original.model_copy(update={"limits": {"max_output_bytes": 500}}))
        failure = wait_for(probe, original.request_id)[0]
        assert failure.format.endswith(".DBFailure")
        assert failure.payload["error"]["code"] == "serialization_failure"
        assert failure.payload["error"]["effect"] == "committed"
        probe.publish_with_guild_route("db.requests", original.model_copy(update={"request_id": "larger-response"}))
        assert wait_for(probe, "larger-response")[0].payload["result"]["replayed"]
    finally:
        database._dependency_resolvers["unidb"].close()
        guild.shutdown()
