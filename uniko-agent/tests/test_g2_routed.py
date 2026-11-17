"""Typed G2 messages cross the real Guild bus with production sender filtering."""

import time

from rustic_ai.core.agents.testutils import ProbeAgent
from rustic_ai.core.guild.builders import AgentBuilder, RouteBuilder
from rustic_ai.core.guild.dsl import GuildTopics
from rustic_ai.core.guild.guild import Guild
from rustic_ai.core.messaging import MessagingConfig
from rustic_ai.core.messaging.core.message import ProcessStatus, RoutingSlip
from rustic_ai.uniko_agent import (
    AddObservationRequest,
    AssertFactRequest,
    BatchItemOutcome,
    BatchSubmitRequest,
    BatchSubmitResponse,
    CommitMemoryUnitRequest,
    CreateGoalRequest,
    CreateTaskRequest,
    EpisodeResponse,
    FactResponse,
    GoalContext,
    GoalContextRequest,
    GoalView,
    MemoryAgent,
    MemoryAgentConfig,
    MemoryScope,
    MemorySource,
    MemoryUnitResponse,
    ObservationResponse,
    ObserveTurnRequest,
    RecordEpisodeRequest,
    TaskStatusResponse,
    TaskView,
    ToolCallSpec,
    UpdateTaskRequest,
)


def test_routed_reporting_workflow(uniko_dependency_spec, filesystem_dependency_spec):
    memory_spec = (
        AgentBuilder(MemoryAgent)
        .set_id("memory")
        .set_name("Memory")
        .set_description("Structured experience")
        .set_properties(MemoryAgentConfig(scope_producers=["reporter"]))
        .listen_to_default_topic(False)
        .add_additional_topic("commands")
        .build_spec()
    )
    reporter_spec = (
        AgentBuilder(ProbeAgent)
        .set_id("reporter")
        .set_name("Reporter")
        .set_description("Reporting tool")
        .listen_to_default_topic(False)
        .add_additional_topic("replies")
        .add_additional_topic(GuildTopics.ERROR_TOPIC)
        .build_spec()
    )
    routes = [
        RouteBuilder(memory_spec)
        .on_message_format(response)
        .set_destination_topics("replies")
        .set_process_status(ProcessStatus.COMPLETED)
        .set_route_times(-1)
        .build()
        for response in (
            GoalView,
            TaskView,
            MemoryUnitResponse,
            EpisodeResponse,
            ObservationResponse,
            FactResponse,
            TaskStatusResponse,
            GoalContext,
            BatchItemOutcome,
            BatchSubmitResponse,
        )
    ]
    guild = Guild(
        id="g2-routed",
        name="Structured workflow",
        description="Typed native workflow",
        organization_id="org",
        execution_engine_clz="rustic_ai.core.guild.execution.sync.sync_exec_engine.SyncExecutionEngine",
        messaging_config=MessagingConfig(
            backend_module="rustic_ai.core.messaging.backend",
            backend_class="InMemoryMessagingBackend",
            backend_config={},
        ),
        dependency_map={"uniko": uniko_dependency_spec, "filesystem": filesystem_dependency_spec},
        routes=RoutingSlip(steps=routes),
    )
    try:
        memory = guild._add_local_agent(memory_spec)
        reporter = guild._add_local_agent(reporter_spec)

        def submit(request):
            reporter.publish_with_guild_route("commands", request)
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                messages = reporter.get_messages()
                if messages:
                    assert len(messages) == 1
                    message = messages[0]
                    reporter.clear_messages()
                    assert not message.format.endswith("MemoryAgentError"), message.payload
                    assert message.process_status == ProcessStatus.COMPLETED
                    return message.payload
                time.sleep(0.01)
            raise AssertionError("The workflow did not emit its terminal response")

        goal = submit(CreateGoalRequest(title="Check evidence", goal_id="objective"))
        assert goal["actor_id"] == "reporter"
        task = submit(CreateTaskRequest(goal_id="objective", title="Search", task_id="search", native_priority=0.7))
        assert task["task_id"] == "search" and task["priority"] == 0.7
        unit = CommitMemoryUnitRequest(
            unit_id="work",
            session_id="evidence",
            turns=[
                ObserveTurnRequest(
                    sender_id="reporter",
                    message_id="message",
                    content="Evidence shows blue sky.",
                    tool_calls=[
                        ToolCallSpec(
                            tool_name="search", call_id="call", json_output={"sky": "blue"}, triggered_by="message"
                        )
                    ],
                )
            ],
        )
        observed = submit(unit)
        assert observed["turns"][0]["tool_calls"][0]["call_id"] == "call"
        assert submit(unit)["was_replay"]
        episode = submit(
            RecordEpisodeRequest(
                action_type="search", episode_id="experience", involved_action_ids=["call"], outcome="success"
            )
        )
        assert episode["episode_id"] == "experience"
        observation = submit(
            AddObservationRequest(
                message_id="message",
                content="Sky is blue",
                subject="Sky",
                predicate="color",
                object="blue",
                scope=MemoryScope(sessions=["evidence"]),
            )
        )
        fact = submit(
            AssertFactRequest(
                subject="Sky",
                predicate="color",
                object="blue",
                supporting_observation_ids=[observation["observation_id"]],
                scope=MemoryScope(sessions=["evidence"]),
            )
        )
        assert fact["fact_id"]
        assert submit(UpdateTaskRequest(task_id="search", action="complete"))["updated"]
        context = submit(GoalContextRequest(goal_id="objective"))
        assert context["episodes"] == [] and not context["episodes_available"]
        native = memory._dependency_resolvers["uniko"].get_or_resolve("org", guild.id, memory.id)
        assert native.query_sync(
            "MATCH (a:Action)-[:PERFORMED_BY]->(p:Participant) RETURN p.participant_id AS owner"
        ) == [{"owner": "reporter"}]
        assert reporter.get_messages() == []
        batch = BatchSubmitRequest(
            session_id="batch",
            batch_id="batch",
            turns=[
                ObserveTurnRequest(
                    sender_id="reporter",
                    message_id="batch-good",
                    content="Valid tool result",
                    tool_calls=[ToolCallSpec(tool_name="lookup", call_id="batch-call", text_output="retained")],
                ).model_dump(mode="json"),
                ObserveTurnRequest(
                    sender_id="reporter",
                    message_id="batch-bad",
                    content="Bad source",
                    tool_calls=[ToolCallSpec(tool_name="lookup", call_id="never-committed", text_output="bad")],
                    attachments=[MemorySource(base64_data="invalid base64")],
                ).model_dump(mode="json"),
            ],
        )
        reporter.publish_with_guild_route("commands", batch)
        messages = reporter.get_messages()
        assert len(messages) == 3
        summary = next(m.payload for m in messages if m.format.endswith("BatchSubmitResponse"))
        assert summary["submitted_count"] == 1
        assert summary["outcomes"][0]["tool_calls"][0]["call_id"] == "batch-call"
        assert not summary["outcomes"][1]["stored"]
        assert native.data.message_sync("batch-bad") is None
        reporter.clear_messages()
        forged = CommitMemoryUnitRequest(
            session_id="evidence",
            unit_id="denied",
            turns=[
                ObserveTurnRequest(
                    sender_id="user",
                    message_id="denied",
                    content="Invalid attribution",
                    tool_calls=[ToolCallSpec(tool_name="lookup", text_output="result")],
                )
            ],
        )
        reporter.publish_with_guild_route("commands", forged)
        errors = reporter.get_messages()
        assert len(errors) == 1 and errors[0].format.endswith("MemoryAgentError")
        assert errors[0].payload["error"] == "unsupported_control"
        assert errors[0].process_status == ProcessStatus.ERROR
        assert native.data.message_sync("denied") is None
        reporter.clear_messages()
    finally:
        guild.shutdown()
