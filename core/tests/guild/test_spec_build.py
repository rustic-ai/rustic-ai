from pydantic import ValidationError
import pytest

from rustic_ai.core import AgentMode, AgentType, Guild, MessagingConfig
from rustic_ai.core.guild.builders import GuildBuilder
from rustic_ai.core.guild.dsl import AgentSpec, GuildSpec
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name

from .sample_agents import (
    DemoAgentGenericWithoutTypedParams,
    DemoAgentGenericWithoutTypedSpec,
    DemoAgentWithMissingGenericAnnotation,
)
from .simple_agent import SimpleAgent


class TestBuildFromSpec:

    exec_engine_clz: str = "rustic_ai.core.guild.execution.sync.sync_exec_engine.SyncExecutionEngine"

    #  Builds a Guild instance from a valid GuildSpec.
    def test_build_from_valid_guild_spec(self, client_properties, org_id):
        guild_spec = GuildSpec(
            name="MyGuild",
            description="A guild for testing",
            properties={
                "backend": {
                    "module": "rustic_ai.core.messaging.backend.embedded_backend",
                    "class": "EmbeddedMessagingBackend",
                    "config": {"auto_start_server": True},
                }
            },
            agents=[
                AgentSpec(
                    name="Agent1",
                    description="First agent",
                    class_name=get_qualified_class_name(SimpleAgent),
                ),
                AgentSpec(
                    name="Agent2",
                    description="Second agent",
                    class_name=get_qualified_class_name(DemoAgentGenericWithoutTypedParams),
                    properties={
                        "prop1": "value1",
                        "prop2": 2,
                    },
                ),
            ],
        )

        guild = GuildBuilder.from_spec(guild_spec).launch(organization_id=org_id)

        assert isinstance(guild, Guild)
        assert guild.name == "MyGuild"
        assert guild.description == "A guild for testing"
        assert guild.get_agent_count() == 2

        agent1 = guild.get_agent_by_name("Agent1")
        agent2 = guild.get_agent_by_name("Agent2")
        assert agent1 is not None
        assert agent2 is not None

        assert agent1.name == "Agent1"
        assert agent1.description == "First agent"
        assert agent1.class_name == get_qualified_class_name(SimpleAgent)

        assert agent2.name == "Agent2"
        assert agent2.description == "Second agent"
        assert agent2.class_name == get_qualified_class_name(DemoAgentGenericWithoutTypedParams)

        assert isinstance(guild.messaging, MessagingConfig)

    #  Builds a Guild instance with multiple agents.
    def test_build_with_multiple_agents(self, client_properties, org_id):
        guild_spec = GuildSpec(
            name="MyGuild",
            description="A guild for testing",
            properties={
                "backend": {
                    "module": "rustic_ai.core.messaging.backend.embedded_backend",
                    "class": "EmbeddedMessagingBackend",
                    "config": {"auto_start_server": True},
                }
            },
            agents=[
                AgentSpec(
                    name="Agent1",
                    description="First agent",
                    class_name=get_qualified_class_name(DemoAgentWithMissingGenericAnnotation),
                    properties={
                        "prop1": "value1",
                    },
                ),
                AgentSpec(
                    name="Agent2",
                    class_name=get_qualified_class_name(DemoAgentGenericWithoutTypedSpec),
                    description="Second agent",
                ),
            ],
        )

        guild = GuildBuilder.from_spec(guild_spec).launch(organization_id=org_id)

        assert guild.get_agent_count() == 2

        agent1 = guild.get_agent_by_name("Agent1")
        agent2 = guild.get_agent_by_name("Agent2")
        assert agent1 is not None
        assert agent2 is not None

        assert agent1.name == "Agent1"
        assert agent1.description == "First agent"
        assert agent1.class_name == get_qualified_class_name(DemoAgentWithMissingGenericAnnotation)
        assert agent1.props.prop1 == "value1"
        assert agent1.props.prop2 == 1

        assert agent2.name == "Agent2"
        assert agent2.description == "Second agent"
        assert agent2.class_name == get_qualified_class_name(DemoAgentGenericWithoutTypedSpec)
        assert agent2.props.prop1 == "default_value"
        assert agent2.props.prop2 == 1

    #  Builds a Guild instance with a storage backend specified in the GuildSpec.
    def test_build_with_storage_backend(self, client_properties, org_id):
        guild_spec = GuildSpec(
            name="MyGuild",
            description="A guild for testing",
            properties={
                "backend": {
                    "module": "rustic_ai.core.messaging.backend.embedded_backend",
                    "class": "EmbeddedMessagingBackend",
                    "config": {"auto_start_server": True},
                }
            },
            agents=[
                AgentSpec(
                    name="Agent1",
                    class_name=get_qualified_class_name(SimpleAgent),
                    description="First agent",
                )
            ],
        )

        guild = GuildBuilder.from_spec(guild_spec).launch(organization_id=org_id)

        assert isinstance(guild.messaging, MessagingConfig)

    #  Builds a Guild instance with an empty agents dictionary.
    def test_build_with_empty_agents(self, client_properties, org_id):
        guild_spec = GuildSpec(
            name="MyGuild",
            description="A guild for testing",
            properties={
                "backend": {
                    "module": "rustic_ai.core.messaging.backend.embedded_backend",
                    "class": "EmbeddedMessagingBackend",
                    "config": {"auto_start_server": True},
                }
            },
            agents=[],
        )

        guild = GuildBuilder.from_spec(guild_spec).launch(organization_id=org_id)

        assert guild.get_agent_count() == 0

    #  Builds a Guild instance with an empty properties dictionary.
    def test_build_with_empty_properties(self, client_properties, org_id):
        guild_spec = GuildSpec(
            name="MyGuild",
            description="A guild for testing",
            properties={},
            agents=[
                AgentSpec(
                    name="Agent1",
                    agent_type=AgentType.BOT,
                    mode=AgentMode.LOCAL,
                    class_name=get_qualified_class_name(SimpleAgent),
                    description="First agent",
                    properties={},
                )
            ],
        )

        guild = GuildBuilder.from_spec(guild_spec).launch(organization_id=org_id)

        assert isinstance(guild, Guild)
        assert guild.name == "MyGuild"
        assert guild.description == "A guild for testing"
        assert guild.get_agent_count() == 1
        agent1 = guild.get_agent_by_name("Agent1")
        assert agent1 is not None

        assert agent1.name == "Agent1"
        assert agent1.description == "First agent"
        assert agent1.class_name == get_qualified_class_name(SimpleAgent)

    def test_null_case(self, org_id):
        guild_spec: GuildSpec = None  # type: ignore

        with pytest.raises(ValueError):
            GuildBuilder.from_spec(guild_spec).launch(organization_id=org_id)

    #  Builds a Guild instance from a valid GuildSpec.
    def test_build_with_invalid_agent_class_name(self, client_properties):
        with pytest.raises(ValidationError):
            GuildSpec(
                name="MyGuild",
                description="A guild for testing",
                properties={
                    "backend": {
                        "module": "rustic_ai.core.messaging.backend.embedded_backend",
                        "class": "EmbeddedMessagingBackend",
                        "config": {"auto_start_server": True},
                    }
                },
                agents=[
                    AgentSpec(
                        name="Agent1",
                        description="First agent",
                        class_name="InvalidAgent",
                        properties={
                            "data-template": {},
                            "client_class": "SimpleClient",
                            "client_properties": client_properties,
                        },
                    ),
                ],
            )
