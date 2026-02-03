from datetime import datetime

import pytest
from sqlmodel import Session, SQLModel, create_engine

from rustic_ai.core.agents.system.guild_manager_agent import GuildManagerAgent
from rustic_ai.core.agents.system.models import (
    RemoveAgentRequest,
    RemoveRoutingRuleRequest,
)
from rustic_ai.core.guild import Agent
from rustic_ai.core.guild.agent import Message, ProcessContext
from rustic_ai.core.guild.agent_ext.mixins.health import (
    Heartbeat,
    HeartbeatStatus,
)
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.guild.metastore import (
    AgentModel,
    GuildModel,
    GuildRoutes,
)
from rustic_ai.core.guild.metastore.models import AgentStatus, GuildStatus, RouteStatus
from rustic_ai.core.messaging.core.message import (
    AgentTag,
    RoutingDestination,
    RoutingRule,
)
from rustic_ai.core.utils import GemstoneGenerator, Priority

# Use in-memory SQLite for testing Metastore interactions
TEST_DB_URL = "sqlite:///:memory:"
id_gen = GemstoneGenerator(0)


class DummyAgent(Agent):
    pass


@pytest.fixture
def metastore_engine():
    engine = create_engine(TEST_DB_URL)
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def guild_manager(metastore_engine):
    # Mocking or creating a lightweight manager wrapper
    # Since GuildManagerAgent is an Agent, we might need to mock its context
    # ideally we unit test the methods directly if possible or override the run method

    # Simpler approach: Create the agent and inject dependencies

    # 1. Create a minimal Guild Spec
    gb = GuildBuilder("test_soft_delete_guild", "Test Soft Delete", "Testing soft delete")
    guild_spec = gb.build_spec()

    # 2. Initialize Manager (mocking props)
    # We might need to monkeypatch the props injection if it relies on agent runtime
    # But let's look at __init__: it takes nothing, reads from self.agent_spec

    # Mock agent_spec props
    class MockProps:
        def __init__(self):
            self.guild_spec = guild_spec
            self.database_url = TEST_DB_URL
            self.organization_id = "test_org"

    class MockSpec:
        def __init__(self):
            self.props = MockProps()
            self.properties = self.props
            self.id = "manager_agent_id"

    # Subclass to inject spec before init
    class TestableGuildManagerAgent(GuildManagerAgent):
        def __init__(self, spec):
            self.agent_spec = spec
            self.id = spec.id
            self.name = "manager"
            self._agent_tag = AgentTag(id=self.id, name=self.name)
            self._route_to_default_topic = False
            self._state = {}
            self._guild_state = {}
            self._id_generator = GemstoneGenerator(0)
            super().__init__()
            # Force overwrite engine with the test fixture engine to share the in-memory DB
            self.engine = metastore_engine

    from unittest.mock import patch

    # We need to patch Metastore.get_engine to return our shared engine
    # because super().__init__ calls it immediately
    with patch("rustic_ai.core.guild.metastore.Metastore.get_engine", return_value=metastore_engine):
        mock_spec = MockSpec()
        agent = TestableGuildManagerAgent(mock_spec)

    # Also need to trigger _launch_guild_agents logic to set up self.guild
    # We can fake it
    # Note: launch() writes to DB. If we use a different engine here, it fails.
    # But gb.launch uses Metastore.get_engine too!

    # We should patch it for the whole function scope or use the patch.
    # Let's keep using the patch for launch too.

    with patch("rustic_ai.core.guild.metastore.Metastore.get_engine", return_value=metastore_engine):
        agent.guild = gb.launch("test_org")

    return agent


def test_soft_delete_agent(guild_manager, metastore_engine):
    # 1. Add agent to DB and Manager
    agent_spec = AgentBuilder(DummyAgent).set_name("victim").set_description("desc").build_spec()

    with Session(metastore_engine) as session:
        # Check initial state
        assert AgentModel.get_by_id(session, guild_manager.guild_id, agent_spec.id) is None

    # Add agent via helper (simulating launch)
    guild_manager._add_agent(agent_spec)

    with Session(metastore_engine) as session:
        model = AgentModel.get_by_id(session, guild_manager.guild_id, agent_spec.id)
        assert model is not None
        assert model.status == AgentStatus.PENDING_LAUNCH

    # 2. Simulate RemoveAgentRequest
    req = RemoveAgentRequest(agent_id=agent_spec.id, guild_id=guild_manager.guild_id)
    ctx = ProcessContext(
        agent=guild_manager,
        method_name="remove_agent",
        message=Message(
            id_obj=id_gen.get_id(Priority.NORMAL),
            sender=AgentTag(id="tester"),
            topics=["control"],
            payload=req.model_dump(),
        ),
        payload_type=RemoveAgentRequest,
    )
    # Mock send methods to avoid errors
    ctx.send = lambda x: None
    ctx._direct_send = lambda **kwargs: None
    ctx.send_error = lambda x: print(f"Error: {x}")

    guild_manager.remove_agent.__wfn__(guild_manager, ctx)

    # 3. Verify Soft Delete
    with Session(metastore_engine) as session:
        model = AgentModel.get_by_id(session, guild_manager.guild_id, agent_spec.id)
        assert model is not None, "Agent record should still exist"
        assert model.status == AgentStatus.DELETED, "Status should be DELETED"

    # 4. Verify Spec Generation Filter
    with Session(metastore_engine) as session:
        guild_model = GuildModel.get_by_id(session, guild_manager.guild_id)
        new_spec = guild_model.to_guild_spec()

        agent_ids = [a.id for a in new_spec.agents]
        assert agent_spec.id not in agent_ids, "Deleted agent should not be in generated spec"


def test_soft_delete_route(guild_manager, metastore_engine):
    # 1. Add Route
    rule = RoutingRule(
        agent=AgentTag(id="router", name="Router"),
        method_name="route_me",
        destination=RoutingDestination(topics=["somewhere", "else"]),
    )

    with Session(metastore_engine) as session:
        route_model = GuildRoutes.from_routing_rule(guild_manager.guild_id, rule)
        route_model.status = RouteStatus.ACTIVE
        session.add(route_model)
        session.commit()

    # 2. Simulate RemoveRoutingRuleRequest
    req = RemoveRoutingRuleRequest(rule_hashid=rule.hashid, guild_id=guild_manager.guild_id)
    ctx = ProcessContext(
        agent=guild_manager,
        method_name="remove_routing_rule",
        message=Message(
            id_obj=id_gen.get_id(Priority.NORMAL),
            sender=AgentTag(id="tester"),
            topics=["control"],
            payload=req.model_dump(),
        ),
        payload_type=RemoveRoutingRuleRequest,
    )
    ctx.send = lambda x: None
    ctx._direct_send = lambda **kwargs: None
    ctx.send_error = lambda x: print(f"Error: {x}")

    guild_manager.remove_routing_rule.__wfn__(guild_manager, ctx)

    # 3. Verify Soft Delete
    with Session(metastore_engine) as session:
        guild_model = GuildModel.get_by_id(session, guild_manager.guild_id)
        # Find the route
        found_route = None
        for r in guild_model.routes:
            # Need to convert to check hashid or check other props
            if r.to_routing_rule().hashid == rule.hashid:
                found_route = r
                break

        assert found_route is not None
        assert found_route.status == RouteStatus.DELETED

    # 4. Verify Spec Generation Filter
    with Session(metastore_engine) as session:
        guild_model = GuildModel.get_by_id(session, guild_manager.guild_id)
        new_spec = guild_model.to_guild_spec()

        # Check routes in slip
        if new_spec.routes:
            hashes = [s.hashid for s in new_spec.routes.steps]
            assert rule.hashid not in hashes, "Deleted route should not be in spec"


def test_guild_status_aggregation(guild_manager, metastore_engine):
    # Setup agents
    agent1 = "agent-1"
    agent2 = "agent-2"

    # Create AgentModels
    with Session(metastore_engine) as session:
        m1 = AgentModel(
            id=agent1, name="A1", class_name="C1", guild_id=guild_manager.guild_id, status=AgentStatus.STARTING
        )
        m2 = AgentModel(
            id=agent2, name="A2", class_name="C2", guild_id=guild_manager.guild_id, status=AgentStatus.STARTING
        )
        session.add_all([m1, m2])
        session.commit()

    # Mock State Manager response
    # The update_agent_status method calls state_manager.get_state
    # We can't easily mock that internal call without refactoring or using `unittest.mock`
    # Let's use `unittest.mock` to patch `state_manager.get_state` on the instance

    from unittest.mock import MagicMock

    # Mock State Manager
    guild_manager.state_manager = MagicMock()

    # Scenario 1: All OK -> RUNNING
    fake_state = {
        agent1: Heartbeat(checktime=datetime.now(), checkstatus=HeartbeatStatus.OK).model_dump(),
        agent2: Heartbeat(checktime=datetime.now(), checkstatus=HeartbeatStatus.OK).model_dump(),
    }

    class MockStateResponse:
        state = fake_state

    guild_manager.state_manager.get_state.return_value = MockStateResponse()

    # Trigger update with one heartbeat
    hb = Heartbeat(checktime=datetime.now(), checkstatus=HeartbeatStatus.OK)
    ctx = ProcessContext(
        agent=guild_manager,
        method_name="update_agent_status",
        message=Message(
            id_obj=id_gen.get_id(Priority.NORMAL),
            sender=AgentTag(id=agent1),
            topics=["health"],
            payload=hb.model_dump(),
        ),
        payload_type=Heartbeat,
    )
    ctx._direct_send = lambda **kwargs: None

    guild_manager.update_agent_status.__wfn__(guild_manager, ctx)

    with Session(metastore_engine) as session:
        guild = GuildModel.get_by_id(session, guild_manager.guild_id)
        assert guild.status == GuildStatus.RUNNING

    # Scenario 2: One ERROR -> ERROR
    fake_state[agent2] = Heartbeat(checktime=datetime.now(), checkstatus=HeartbeatStatus.ERROR).model_dump()
    guild_manager.state_manager.get_state.return_value = MockStateResponse()

    # We need to update context payload for next call
    hb_error = Heartbeat(checktime=datetime.now(), checkstatus=HeartbeatStatus.ERROR)

    # Recreate context or update message
    # Easier to recreate
    ctx = ProcessContext(
        agent=guild_manager,
        method_name="update_agent_status",
        message=Message(
            id_obj=id_gen.get_id(Priority.NORMAL),
            sender=AgentTag(id=agent1),
            topics=["health"],
            payload=hb_error.model_dump(),
        ),
        payload_type=Heartbeat,
    )
    ctx._direct_send = lambda **kwargs: None

    guild_manager.update_agent_status.__wfn__(guild_manager, ctx)

    with Session(metastore_engine) as session:
        guild = GuildModel.get_by_id(session, guild_manager.guild_id)
        assert guild.status == GuildStatus.ERROR
