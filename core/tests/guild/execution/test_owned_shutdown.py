"""Shutdown respects agent, resolver, guild and process ownership."""

import multiprocessing
import pickle
from unittest.mock import Mock
from uuid import uuid4

import pytest

from rustic_ai.core.agents.testutils import ProbeAgent
from rustic_ai.core.guild.agent_ext.depends.dependency_resolver import (
    DependencyResolver,
    DependencySpec,
)
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.guild.execution.multiprocess.multiprocess_agent_wrapper import (
    MultiProcessAgentWrapper,
)
from rustic_ai.core.guild.execution.multiprocess.multiprocess_exec_engine import (
    MultiProcessExecutionEngine,
)


class CleanupProbe(ProbeAgent):
    def __init__(self):
        ProbeAgent.__init__(self)
        self.shutdown_count = 0

    def on_shutdown(self):
        self.shutdown_count += 1


class OwnedResolver(DependencyResolver):
    def __init__(self):
        super().__init__()
        self.shutdown_count = 0
        self.value = Mock()

    def resolve(self, org_id, guild_id, agent_id):
        return self.value

    def shutdown(self):
        self.shutdown_count += 1


def build(engine, count=2):
    builder = GuildBuilder("cleanup-" + uuid4().hex, "Cleanup", "Owned shutdown")
    builder.set_execution_engine("rustic_ai.core.guild.execution." + engine)
    builder.set_dependency_map({"resource": DependencySpec(class_name=OwnedResolver.get_qualified_class_name())})
    for index in range(count):
        builder.add_agent_spec(
            AgentBuilder(CleanupProbe)
            .set_id("probe-" + str(index))
            .set_name("Probe " + str(index))
            .set_description("Lifecycle test")
            .add_additional_dependency("resource")
            .build_spec()
        )
    return builder.launch("cleanup-org")


def wrapper(guild, agent_id):
    result = guild.execution_engine.agent_tracker.get_agent_wrapper(guild.id, agent_id)
    if hasattr(result, "initialization_complete"):
        assert result.initialization_complete.wait(5)
    return result


@pytest.mark.parametrize(
    "engine",
    ["sync.sync_exec_engine.SyncExecutionEngine", "multithreaded.multithreaded_exec_engine.MultiThreadedEngine"],
)
def test_every_owned_agent_stops_other_guild_survives(engine):
    first = build(engine)
    second = build(engine, count=2)
    try:
        wrappers = [wrapper(first, "probe-" + str(index)) for index in range(2)]
        survivor = wrapper(second, "probe-0")
        recorder = wrapper(second, "probe-1").agent
        historical_id = survivor.agent.publish_dict("default_topic", {"history": "keep"}).to_int()
        assert recorder.get_messages()
        assert survivor.messaging.backend.get_messages_by_id(second.id, [historical_id])
        resolvers = [w.agent._dependency_resolvers["resource"] for w in wrappers]
        for resolver in resolvers:
            resolver.get_or_resolve("cleanup-org", first.id, "probe")
        child = OwnedResolver()
        resolvers[0]._injectors["child"] = child
        first.shutdown()
        first.shutdown()
        assert [w.agent.shutdown_count for w in wrappers] == [1, 1]
        assert [r.shutdown_count for r in resolvers] == [1, 1]
        assert child.shutdown_count == 1
        for resolver in resolvers:
            resolver.value.shutdown.assert_not_called()
        assert survivor.agent.shutdown_count == 0
        assert survivor.messaging.backend.get_messages_by_id(second.id, [historical_id])
        survivor.agent.publish_dict("default_topic", {"history": "still-running"})
        assert len(recorder.get_messages()) == 2
        assert second.execution_engine.is_agent_running(second.id, "probe-0")
        assert second.execution_engine.find_agents_by_name(second.id, "Probe 0")
    finally:
        first.shutdown()
        second.shutdown()


def test_hook_failure_still_closes_owned_dependencies_and_messaging():
    guild = build("sync.sync_exec_engine.SyncExecutionEngine", count=1)
    w = wrapper(guild, "probe-0")
    resolver = w.agent._dependency_resolvers["resource"]
    w.agent.on_shutdown = Mock(side_effect=RuntimeError("hook failed"))
    guild.shutdown()
    assert resolver.shutdown_count == 1
    assert not w.messaging.clients


def test_borrowed_resolver_is_not_closed():
    guild = build("sync.sync_exec_engine.SyncExecutionEngine", count=1)
    w = wrapper(guild, "probe-0")
    borrowed = OwnedResolver()
    w.agent._dependency_resolvers = {"resource": borrowed}
    w.agent._owned_dependency_resolvers = ()
    guild.shutdown()
    assert borrowed.shutdown_count == 0


def wait_for_stop(event):
    event.wait(15)


def test_empty_multiprocess_engine_preserves_unrelated_child():
    ctx = multiprocessing.get_context("spawn")
    event = ctx.Event()
    child = ctx.Process(target=wait_for_stop, args=(event,))
    child.start()
    engine = MultiProcessExecutionEngine(guild_id="owned", organization_id="cleanup-org", max_processes=1)
    try:
        engine.shutdown()
        assert child.is_alive()
    finally:
        event.set()
        child.join(timeout=5)
        if child.is_alive():
            child.terminate()
            child.join(timeout=5)


def test_multiprocess_exception_path_runs_common_cleanup():
    guild = build("sync.sync_exec_engine.SyncExecutionEngine", count=1)
    original = wrapper(guild, "probe-0")
    spec = original.agent_spec
    child_wrapper = MultiProcessAgentWrapper(original.guild_spec, spec, original.messaging_config, 1)
    # This test exercises the child's run/finally path without spawning another
    # transport, while the separate process test proves process ownership.
    child_wrapper.agent = original.agent
    child_wrapper.messaging = original.messaging
    child_wrapper.messaging_owned = True
    child_wrapper.initialize_agent = Mock(side_effect=RuntimeError("initialization failed"))
    with pytest.raises(RuntimeError, match="initialization failed"):
        child_wrapper.run()
    assert original.agent.shutdown_count == 1
    assert original.agent._dependency_resolvers["resource"].shutdown_count == 1
    original._shutdown_complete = True
    guild.shutdown()


def test_process_wrapper_remains_serializable_before_launch():
    builder = GuildBuilder("serialize", "Serialize", "Process wrapper")
    spec = (
        AgentBuilder(CleanupProbe)
        .set_id("probe")
        .set_name("Probe")
        .set_description("Serializable wrapper")
        .build_spec()
    )
    from rustic_ai.core.messaging import MessagingConfig

    wrapper = MultiProcessAgentWrapper(
        builder.build_spec(),
        spec,
        MessagingConfig(
            backend_module="rustic_ai.core.messaging.backend",
            backend_class="InMemoryMessagingBackend",
            backend_config={},
        ),
        1,
    )
    restored = pickle.loads(pickle.dumps(wrapper))
    assert restored.agent_spec.id == "probe"
    assert not restored._shutdown_complete
    with restored._shutdown_lock:
        restored.shutdown()


def test_unsubscribe_failure_does_not_skip_resource_cleanup():
    guild = build("sync.sync_exec_engine.SyncExecutionEngine", count=1)
    w = wrapper(guild, "probe-0")
    resolver = w.agent._dependency_resolvers["resource"]
    w.messaging.unsubscribe = Mock(side_effect=RuntimeError("transport already closed"))
    guild.shutdown()
    assert resolver.shutdown_count == 1
    assert w.agent.shutdown_count == 1
    assert not w.messaging.clients
