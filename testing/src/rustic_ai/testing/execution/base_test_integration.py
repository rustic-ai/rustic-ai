from abc import ABC, abstractmethod
import time

import pytest

from rustic_ai.core.guild.builders import AgentBuilder
from rustic_ai.core.guild.dsl import AgentSpec
from rustic_ai.core.guild.execution.sync.sync_exec_engine import SyncExecutionEngine
from rustic_ai.core.guild.guild import Guild

from .integration_agents import InitiatorProbeAgent, LocalTestAgent, ResponderProbeAgent


class IntegrationTestABC(ABC):
    @abstractmethod
    @pytest.fixture
    def messaging(self, guild_id):
        pass

    @abstractmethod
    @pytest.fixture
    def execution_engine(self) -> str:
        pass

    @pytest.fixture
    def guild_id(self) -> str:
        return "test_guild_id"

    @pytest.fixture
    def wait_time(self) -> float:
        return 0.1

    @pytest.fixture
    def guild(self, wait_time, messaging, execution_engine, guild_id, org_id):
        guild = Guild(
            id=guild_id,
            name="Test Guild",
            description="A guild for integration testing",
            messaging_config=messaging,
            execution_engine_clz=execution_engine,
            organization_id=org_id,
        )
        yield guild
        time.sleep(wait_time * 5)  # Allow some time for cleanup
        guild.shutdown()

    @pytest.fixture
    def initiator_agent(self) -> AgentSpec:
        return (
            AgentBuilder(InitiatorProbeAgent)
            .set_id("initiator")
            .set_name("Initiator Agent")
            .set_description("Initiates communication")
            .build_spec()
        )

    @pytest.fixture
    def responder_agent(self) -> AgentSpec:
        return (
            AgentBuilder(ResponderProbeAgent)
            .set_id("responder")
            .set_name("Responder Agent")
            .set_description("Responds to communication")
            .build_spec()
        )

    @pytest.fixture
    def local_test_agent_spec(self) -> AgentSpec:
        # Instantiate the local test agent with the same message bus
        return (
            AgentBuilder(LocalTestAgent)
            .set_id("local_test")
            .set_name("LocalTestAgent")
            .set_description("Local test agent for integration testing")
            .build_spec()
        )

    def test_agents_communication(
        self,
        wait_time: float,
        guild: Guild,
        local_test_agent_spec: AgentSpec,
        initiator_agent: AgentSpec,
        responder_agent: AgentSpec,
    ):
        execution_engine = guild._get_execution_engine()
        # Add both agents to the guild
        guild.launch_agent(initiator_agent)
        guild.launch_agent(responder_agent)

        # Test if the agent is in the execution engine
        agents = execution_engine.get_agents_in_guild(guild.id)
        assert len(agents) == 2

        ia = execution_engine.find_agents_by_name(guild.id, "Initiator Agent")
        assert len(ia) == 1

        iair = execution_engine.is_agent_running(guild.id, ia[0].id)
        assert iair is True

        ra = execution_engine.find_agents_by_name(guild.id, "Responder Agent")
        assert len(ra) == 1

        rair = execution_engine.is_agent_running(guild.id, ra[0].id)
        assert rair is True

        local_exec_engine = SyncExecutionEngine(guild_id=guild.id, organization_id=guild.organization_id)
        local_test_agent = guild._add_local_agent(local_test_agent_spec, local_exec_engine)

        # Give more time for all agents to initialize fully, especially for Ray/distributed execution
        time.sleep(max(wait_time * 10, 1.0))

        # Initiator sends a message to trigger communication
        local_test_agent.publish_initial_message()

        # Allow more time for message processing in distributed scenarios
        # Consider using a more sophisticated synchronization mechanism for real-world scenarios
        time.sleep(max(wait_time * 30, 3.0))

        # Assertions to verify communication flow
        # Ensure the local test agent captured the messages as expected
        assert len(local_test_agent.captured_messages) == 2

        msg0 = local_test_agent.captured_messages[0]
        msg1 = local_test_agent.captured_messages[1]

        if msg0.sender.id == "initiator":
            first_msg = msg0
            second_msg = msg1
        else:
            first_msg = msg1
            second_msg = msg0

        assert first_msg.topics == "default_topic"
        assert first_msg.payload.get("content", "") == "Hello Responder!"
        assert first_msg.sender.id == "initiator"
        assert second_msg.topics == "default_topic"
        assert second_msg.payload.get("content", "") == f"Acknowledged: {first_msg.id}"
        assert second_msg.sender.id == "responder"

        # Clear the messages for the next test
        local_test_agent.clear_messages()

        # Remove responder agent
        guild.remove_agent(ra[0].id)

        # Test if the agent is removed from the execution engine
        agents2 = execution_engine.get_agents_in_guild(guild.id)
        assert len(agents2) >= 1  # Initiator agent and local test agent (in case of local execution engine)

        ra2 = execution_engine.find_agents_by_name(guild.id, "Responder Agent")
        assert len(ra2) == 0

        rair2 = execution_engine.is_agent_running(guild.id, ra[0].id)
        assert rair2 is False

        # Send a new message to ensure that the responder agent is no longer processing messages
        local_test_agent.publish_initial_message()

        time.sleep(max(wait_time * 30, 3.0))

        # Ensure that the responder agent did not process the message
        assert len(local_test_agent.captured_messages) == 1

        msgX = local_test_agent.captured_messages[0]
        assert msgX.topics == "default_topic"
        assert msgX.payload.get("content", "") == "Hello Responder!"
        assert msgX.sender.id == "initiator"
