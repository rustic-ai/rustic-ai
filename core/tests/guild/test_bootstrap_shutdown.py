import time
from uuid import uuid4

import pytest

from rustic_ai.core.agents.testutils.echo_agent import EchoAgent
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder


@pytest.mark.parametrize(
    "engine",
    ["sync.sync_exec_engine.SyncExecutionEngine", "multithreaded.multithreaded_exec_engine.MultiThreadedEngine"],
)
def test_bootstrap_shutdown_releases_manager_owned_agents(database, engine):
    builder = (
        GuildBuilder("shutdown-" + uuid4().hex, "Shutdown ownership", "Manager-owned actor lifecycle")
        .set_property("execution_engine", "rustic_ai.core.guild.execution." + engine)
        .add_agent_spec(AgentBuilder(EchoAgent).set_id("echo").set_name("Echo").set_description("Echo").build_spec())
    )
    guild = builder.bootstrap(database, "shutdown-tests")
    try:
        manager_spec = guild.list_agents()[0]
        manager_wrapper = guild.execution_engine.agent_tracker.get_agent_wrapper(guild.id, manager_spec.id)
        if hasattr(manager_wrapper, "initialization_complete"):
            assert manager_wrapper.initialization_complete.wait(30)
        manager = manager_wrapper.agent
        deadline = time.monotonic() + 30
        while getattr(manager, "guild", None) is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert manager.guild is not None
        owned_engine = manager.guild.execution_engine
        actor = owned_engine.agent_tracker.get_agent_wrapper(guild.id, "echo")
        assert actor is not None
        if hasattr(actor, "initialization_complete"):
            assert actor.initialization_complete.wait(30)
        guild.shutdown()
        assert actor._shutdown_complete
        assert not owned_engine.owned_agents
        assert owned_engine.agent_tracker.get_agent_wrapper(guild.id, "echo") is None
        guild.shutdown()
        assert actor._shutdown_complete
    finally:
        guild.shutdown()


@pytest.mark.parametrize(
    "engine",
    ["sync.sync_exec_engine.SyncExecutionEngine", "multithreaded.multithreaded_exec_engine.MultiThreadedEngine"],
)
def test_shutdown_during_inner_launch_closes_late_candidate(database, monkeypatch, engine):
    import threading

    from rustic_ai.core.guild.builders import GuildHelper

    identifier = "early-" + uuid4().hex
    entered, resume = threading.Event(), threading.Event()
    guilds, results, errors = [], [], []
    original_shallow = GuildHelper.shallow_guild_from_spec
    original_launch = GuildBuilder.launch

    def capture_shallow(*args, **kwargs):
        candidate = original_shallow(*args, **kwargs)
        if candidate.id == identifier:
            guilds.append(candidate)
        return candidate

    def hold_return(builder, *args, **kwargs):
        candidate = original_launch(builder, *args, **kwargs)
        if candidate.id == identifier:
            entered.set()
            assert resume.wait(20)
        return candidate

    monkeypatch.setattr(GuildHelper, "shallow_guild_from_spec", staticmethod(capture_shallow))
    monkeypatch.setattr(GuildBuilder, "launch", hold_return)
    builder = (
        GuildBuilder(identifier, "Early shutdown", "Stop before candidate adoption")
        .set_property("execution_engine", "rustic_ai.core.guild.execution." + engine)
        .add_agent_spec(AgentBuilder(EchoAgent).set_id("echo").set_name("Echo").set_description("Echo").build_spec())
    )

    def bootstrap():
        try:
            results.append(builder.bootstrap(database, "shutdown-tests"))
        except BaseException as error:
            errors.append(error)

    worker = threading.Thread(target=bootstrap)
    worker.start()
    manager_wrapper = None
    try:
        assert entered.wait(30)
        assert len(guilds) == 2
        shallow, candidate = guilds
        manager_wrapper = shallow.execution_engine.agent_tracker.get_agent_wrapper(
            identifier, GuildHelper.get_manager_agent_id(identifier)
        )
        assert manager_wrapper is not None and manager_wrapper.agent.guild is None
        actor = candidate.execution_engine.agent_tracker.get_agent_wrapper(identifier, "echo")
        assert actor is not None
        if hasattr(actor, "initialization_complete"):
            assert actor.initialization_complete.wait(30)
        assert actor.agent is not None and not actor._shutdown_complete
        shallow.shutdown()
        assert manager_wrapper._shutdown_complete
        resume.set()
        worker.join(30)
        assert not worker.is_alive() and not errors and len(results) == 1
        if hasattr(manager_wrapper, "initialization_complete"):
            assert manager_wrapper.initialization_complete.wait(30)
        assert actor._shutdown_complete
        assert not candidate.execution_engine.owned_agents
        assert candidate.execution_engine.agent_tracker.get_agent_wrapper(identifier, "echo") is None
        assert manager_wrapper.agent.guild is None
        shallow.shutdown()
    finally:
        resume.set()
        worker.join(30)
        if manager_wrapper is not None and hasattr(manager_wrapper, "agent_thread"):
            manager_wrapper.agent_thread.join(30)
        for candidate in reversed(guilds):
            candidate.shutdown()


@pytest.mark.parametrize("method", ["launch", "load_or_launch"])
@pytest.mark.parametrize(
    "engine",
    ["sync.sync_exec_engine.SyncExecutionEngine", "multithreaded.multithreaded_exec_engine.MultiThreadedEngine"],
)
def test_partial_builder_failure_releases_already_started_actor(monkeypatch, method, engine):
    from rustic_ai.core.guild.builders import GuildHelper
    from rustic_ai.core.guild.guild import Guild

    identifier = "partial-" + uuid4().hex
    guilds, actors = [], []
    original_shallow = GuildHelper.shallow_guild_from_spec
    original_start = Guild.launch_agent
    failure = RuntimeError("Second actor cannot start")

    def capture_shallow(*args, **kwargs):
        candidate = original_shallow(*args, **kwargs)
        if candidate.id == identifier:
            guilds.append(candidate)
        return candidate

    def fail_second(guild, spec, execution_engine=None):
        if guild.id == identifier and spec.id == "broken":
            raise failure
        original_start(guild, spec, execution_engine)
        if guild.id == identifier and spec.id == "echo":
            actor = guild.execution_engine.agent_tracker.get_agent_wrapper(identifier, "echo")
            if hasattr(actor, "initialization_complete"):
                assert actor.initialization_complete.wait(30)
            assert actor.agent is not None
            actors.append(actor)

    monkeypatch.setattr(GuildHelper, "shallow_guild_from_spec", staticmethod(capture_shallow))
    monkeypatch.setattr(Guild, "launch_agent", fail_second)
    builder = GuildBuilder(identifier, "Partial startup", "Clean up on actor startup failure").set_property(
        "execution_engine", "rustic_ai.core.guild.execution." + engine
    )
    for name in ["echo", "broken"]:
        builder.add_agent_spec(
            AgentBuilder(EchoAgent).set_id(name).set_name(name).set_description("Startup actor").build_spec()
        )
    try:
        with pytest.raises(RuntimeError) as raised:
            getattr(builder, method)("shutdown-tests")
        assert raised.value is failure
        assert len(actors) == len(guilds) == 1
        assert actors[0]._shutdown_complete
        assert not guilds[0].execution_engine.owned_agents
        assert guilds[0].execution_engine.agent_tracker.get_agent_wrapper(identifier, "echo") is None
    finally:
        for candidate in reversed(guilds):
            candidate.shutdown()


@pytest.mark.parametrize(
    "engine",
    ["sync.sync_exec_engine.SyncExecutionEngine", "multithreaded.multithreaded_exec_engine.MultiThreadedEngine"],
)
def test_failed_load_preserves_registered_actor_owned_by_another_engine(monkeypatch, engine):
    from rustic_ai.core.guild.guild import Guild

    identifier = "shared-" + uuid4().hex
    builder = (
        GuildBuilder(identifier, "Existing actor", "Preserve another engine's actor")
        .set_property("execution_engine", "rustic_ai.core.guild.execution." + engine)
        .add_agent_spec(
            AgentBuilder(EchoAgent).set_id("echo").set_name("Echo").set_description("Existing").build_spec()
        )
    )
    owner = builder.launch("shutdown-tests")
    actor = owner.execution_engine.agent_tracker.get_agent_wrapper(identifier, "echo")
    if hasattr(actor, "initialization_complete"):
        assert actor.initialization_complete.wait(30)
    original_start = Guild.launch_agent

    def fail_new(guild, spec, execution_engine=None):
        if guild.id == identifier and spec.id == "broken":
            raise RuntimeError("New actor cannot start")
        return original_start(guild, spec, execution_engine)

    monkeypatch.setattr(Guild, "launch_agent", fail_new)
    builder.add_agent_spec(
        AgentBuilder(EchoAgent).set_id("broken").set_name("Broken").set_description("New actor").build_spec()
    )
    try:
        with pytest.raises(RuntimeError, match="New actor cannot start"):
            builder.load_or_launch("shutdown-tests")
        assert not actor._shutdown_complete
        assert owner.execution_engine.agent_tracker.get_agent_wrapper(identifier, "echo") is actor
        assert (identifier, "echo") in owner.execution_engine.owned_agents
    finally:
        owner.shutdown()
