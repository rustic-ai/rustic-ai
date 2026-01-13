import pytest

from rustic_ai.core.guild.builders import AgentBuilder
from rustic_ai.core.guild.dsl import AgentSpec
from rustic_ai.core.guild.guild import Guild
from rustic_ai.core.messaging import MessagingConfig

from .simple_agent import SimpleAgent


class TestGuild:

    exec_engine_clz: str = "rustic_ai.core.guild.execution.sync.sync_exec_engine.SyncExecutionEngine"

    @pytest.fixture
    def messaging(self):
        return MessagingConfig(
            backend_module="rustic_ai.core.messaging.backend",
            backend_class="InMemoryMessagingBackend",
            backend_config={},
        )

    @pytest.fixture
    def agent_spec(self) -> AgentSpec:
        agent_id = "p1"
        name = "John"
        description = "A human agent"

        return AgentBuilder(SimpleAgent).set_id(agent_id).set_name(name).set_description(description).build_spec()

    @pytest.fixture
    def guild(self, messaging, org_id):
        guild_id = "e1"
        name = "Guild1"
        description = "Test Guild"
        execution_engine = TestGuild.exec_engine_clz
        guild = Guild(
            id=guild_id,
            name=name,
            description=description,
            execution_engine_clz=execution_engine,
            messaging_config=messaging,
            organization_id=org_id,
        )
        yield guild
        guild.shutdown()

    def test_guild_initialization(self, messaging, org_id):
        guild_id = "e1"
        name = "Guild1"
        description = "Test Guild"

        execution_engine = TestGuild.exec_engine_clz

        guild = Guild(
            id=guild_id,
            name=name,
            description=description,
            execution_engine_clz=execution_engine,
            messaging_config=messaging,
            organization_id=org_id,
        )

        assert guild.id == guild_id
        assert guild.name == name
        assert guild.description == description
        assert guild.messaging == messaging

    def test_guild_initialization_with_messaging_config(self, org_id):
        # Use InMemoryMessagingBackend for testing
        messaging_config = MessagingConfig(
            backend_module="rustic_ai.core.messaging.backend",
            backend_class="InMemoryMessagingBackend",
            backend_config={},
        )

        guild_id = "e1"
        name = "Guild1"
        description = "Test Guild"

        execution_engine = TestGuild.exec_engine_clz

        guild = Guild(
            id=guild_id,
            name=name,
            description=description,
            execution_engine_clz=execution_engine,
            messaging_config=messaging_config,
            organization_id=org_id,
        )

        assert guild.id == guild_id
        assert guild.name == name
        assert guild.description == description
        assert guild.messaging == messaging_config

    def test_launch_agent(self, guild: Guild):
        new_agent_id = "p2"
        new_agent: AgentSpec = (
            AgentBuilder(SimpleAgent)
            .set_id(new_agent_id)
            .set_name("Jane")
            .set_description("Another human agent")
            .build_spec()
        )

        guild.launch_agent(new_agent)

        agent_from_guild = guild.get_agent(new_agent_id)
        assert agent_from_guild is not None
        assert agent_from_guild.name == new_agent.name
        assert agent_from_guild.description == new_agent.description
        assert agent_from_guild.id == new_agent.id

    # Test the private method _add_local_agent just to make sure someone doesn't accidentally break it
    def test_add_local_agent(self, guild: Guild):
        new_agent_id = "p2"
        new_agent_spec = (
            AgentBuilder(SimpleAgent)
            .set_id(new_agent_id)
            .set_name("Jane")
            .set_description("Another human agent")
            .build_spec()
        )

        new_agent = guild._add_local_agent(new_agent_spec)

        agent_from_guild = guild.get_agent(new_agent_id)
        assert agent_from_guild is not None
        assert agent_from_guild.name == new_agent.name
        assert agent_from_guild.description == new_agent.description
        assert agent_from_guild.id == new_agent.id

    def test_remove_agent(self, guild: Guild, agent_spec: AgentSpec):
        guild.launch_agent(agent_spec)
        guild.remove_agent(agent_spec.id)
        assert guild.get_agent(agent_spec.id) is None

        with pytest.raises(ValueError):
            guild.remove_agent("invalid_id")

    def test_list_agents(self, guild: Guild, agent_spec: AgentSpec):
        guild.launch_agent(agent_spec)
        agents = guild.list_agents()
        assert len(agents) == 1
        assert agents[0] == agent_spec

    def test_guild_to_spec(self, guild: Guild, agent_spec: AgentSpec):
        guild.launch_agent(agent_spec)
        details = guild.to_spec()
        assert details.id == guild.id
        assert len(details.agents) == 1
        assert details.agents[0].id == agent_spec.id
