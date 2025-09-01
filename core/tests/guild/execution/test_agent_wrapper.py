import pytest

from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.guild.dsl import AgentSpec
from rustic_ai.core.guild.execution.agent_wrapper import AgentWrapper
from rustic_ai.core.messaging import (
    MessageTrackingClient,
    MessagingConfig,
    MessagingInterface,
)

from ..simple_agent import SimpleAgent

# Assuming all necessary imports are defined at the top of the file


class MockAgentWrapper(AgentWrapper):
    def run(self) -> None:
        # Dummy implementation for testing purposes.
        pass


class TestAgentWrapper:

    @pytest.fixture
    def guild_spec(self):
        return GuildBuilder(
            "wrapper_test_guild",
            "Wrapper Test Guild",
            "A test guild",
        ).build_spec()

    @pytest.fixture
    def agent_spec(self) -> AgentSpec:
        agent_id = "p1"
        name = "John"
        description = "A human agent"

        return AgentBuilder(SimpleAgent).set_id(agent_id).set_name(name).set_description(description).build_spec()

    @pytest.fixture
    def messaging_config(self):
        return MessagingConfig(
            backend_module="rustic_ai.core.messaging.backend",
            backend_class="InMemoryMessagingBackend",
            backend_config={},
        )

    def test_initialize_agent_with_messaging_config(self, agent_spec, messaging_config, guild_spec):
        machine_id = 1

        agent_wrapper = MockAgentWrapper(
            guild_spec=guild_spec,
            agent_spec=agent_spec,
            messaging_config=messaging_config,
            machine_id=machine_id,
            client_type=MessageTrackingClient,
            client_properties={},
        )

        # Perform common initialization tasks, which includes setting up the message bus from config
        agent_wrapper.initialize_agent()

        # Assertions to verify the message bus and client are initialized correctly
        assert isinstance(agent_wrapper.messaging, MessagingInterface), "Messaging Interface should be initialized"
        assert (
            agent_wrapper.messaging.backend.__class__.__name__ == "InMemoryMessagingBackend"
        ), "Storage should be InMemoryMessagingBackend"
        assert agent_wrapper.agent is not None
        assert (
            agent_wrapper.agent._client.__class__.__name__ == "MessageTrackingClient"
        ), "Client should be MessageTrackingClient"
        assert agent_wrapper.agent._client.id == f"{guild_spec.id}${agent_spec.id}", "Client ID should be set"
        assert agent_wrapper.agent._client.name == agent_spec.name, "Client name should be set"

    def test_initialize_agent_with_messaging_instance(self, agent_spec, guild_spec):
        messaging_config = MessagingConfig(
            backend_module="rustic_ai.core.messaging.backend",
            backend_class="InMemoryMessagingBackend",
            backend_config={},
        )

        agent_wrapper = MockAgentWrapper(
            guild_spec=guild_spec,
            agent_spec=agent_spec,
            messaging_config=messaging_config,  # Passing the actual Messaging Interface
            machine_id=1,
            client_type=MessageTrackingClient,  # Using the actual client type
            client_properties={},
        )

        agent_wrapper.initialize_agent()

        assert isinstance(agent_wrapper.messaging, MessagingInterface), "Messaging Interface should be initialized"
        assert agent_wrapper.agent is not None
        assert (
            agent_wrapper.agent._client.__class__.__name__ == "MessageTrackingClient"
        ), "Client should be MessageTrackingClient"
        assert agent_wrapper.agent._client.id == f"{guild_spec.id}${agent_spec.id}", "Client ID should be set"
        assert agent_wrapper.agent._client.name == agent_spec.name, "Client name should be set"
