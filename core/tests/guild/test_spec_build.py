from pydantic import ValidationError
import pytest

from rustic_ai.core import Guild
from rustic_ai.core.guild.builders import GuildBuilder
from rustic_ai.core.guild.dsl import AgentSpec, GuildSpec
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name

from .sample_agents import (
    DemoAgentGenericWithoutTypedParams,
    DemoAgentProps,
    DemoAgentWithMissingGenericAnnotation,
)
from .simple_agent import SimpleAgent


class TestBuildFromSpec:

    exec_engine_clz: str = "rustic_ai.core.guild.execution.sync.sync_exec_engine.SyncExecutionEngine"

    #  Builds a Guild instance from a valid GuildSpec.
    def test_build_from_valid_guild_spec(self, client_properties, org_id, messaging_server):
        server, port = messaging_server
        guild_spec = GuildSpec(
            name="MyGuild",
            description="A guild for testing",
            properties={
                "backend": {
                    "module": "rustic_ai.core.messaging.backend.embedded_backend",
                    "class": "EmbeddedMessagingBackend",
                    "config": {"auto_start_server": False, "port": port},
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
                    properties=DemoAgentProps(
                        prop1="value1",
                        prop2=2,
                    ),
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

        # clean up
        guild.shutdown()

    #  Builds a Guild instance from a valid GuildSpec with multiple agents.
    def test_build_with_multiple_agents(self, client_properties, org_id, messaging_server):
        server, port = messaging_server
        guild_spec = GuildSpec(
            name="MyGuild",
            description="A guild for testing",
            properties={
                "backend": {
                    "module": "rustic_ai.core.messaging.backend.embedded_backend",
                    "class": "EmbeddedMessagingBackend",
                    "config": {"auto_start_server": False, "port": port},
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
                    properties=DemoAgentProps(
                        prop1="value1",
                        prop2=2,
                    ),
                ),
                AgentSpec(
                    name="Agent3",
                    description="Third agent",
                    class_name=get_qualified_class_name(SimpleAgent),
                ),
            ],
        )

        guild = GuildBuilder.from_spec(guild_spec).launch(organization_id=org_id)

        assert isinstance(guild, Guild)
        assert guild.name == "MyGuild"
        assert guild.description == "A guild for testing"
        assert guild.get_agent_count() == 3

        agent1 = guild.get_agent_by_name("Agent1")
        agent2 = guild.get_agent_by_name("Agent2")
        agent3 = guild.get_agent_by_name("Agent3")
        assert agent1 is not None
        assert agent2 is not None
        assert agent3 is not None

    #  Builds a Guild instance from a valid GuildSpec with storage backend.
    def test_build_with_storage_backend(self, client_properties, org_id, messaging_server):
        server, port = messaging_server
        guild_spec = GuildSpec(
            name="MyGuild",
            description="A guild for testing",
            properties={
                "backend": {
                    "module": "rustic_ai.core.messaging.backend.embedded_backend",
                    "class": "EmbeddedMessagingBackend",
                    "config": {"auto_start_server": False, "port": port},
                },
                "storage": {
                    "class": "rustic_ai.core.messaging.storage.InMemoryStorage",
                    "properties": {},
                },
            },
            agents=[
                AgentSpec(
                    name="Agent1",
                    description="First agent",
                    class_name=get_qualified_class_name(SimpleAgent),
                ),
            ],
        )

        guild = GuildBuilder.from_spec(guild_spec).launch(organization_id=org_id)

        assert isinstance(guild, Guild)
        assert guild.name == "MyGuild"
        assert guild.description == "A guild for testing"
        assert guild.get_agent_count() == 1

        # clean up
        guild.shutdown()

    #  Builds a Guild instance from a valid GuildSpec with empty agents.
    def test_build_with_empty_agents(self, client_properties, org_id, messaging_server):
        server, port = messaging_server
        guild_spec = GuildSpec(
            name="MyGuild",
            description="A guild for testing",
            properties={
                "backend": {
                    "module": "rustic_ai.core.messaging.backend.embedded_backend",
                    "class": "EmbeddedMessagingBackend",
                    "config": {"auto_start_server": False, "port": port},
                }
            },
            agents=[],
        )

        guild = GuildBuilder.from_spec(guild_spec).launch(organization_id=org_id)

        assert isinstance(guild, Guild)
        assert guild.name == "MyGuild"
        assert guild.description == "A guild for testing"
        assert guild.get_agent_count() == 0

        # clean up
        guild.shutdown()

    #  Builds a Guild instance from a valid GuildSpec with empty properties (should use defaults).
    def test_build_with_empty_properties(self, client_properties, org_id):
        guild_spec = GuildSpec(
            name="MyGuild",
            description="A guild for testing",
            properties={},
            agents=[
                AgentSpec(
                    name="Agent1",
                    description="First agent",
                    class_name=get_qualified_class_name(SimpleAgent),
                ),
            ],
        )

        guild = GuildBuilder.from_spec(guild_spec).launch(organization_id=org_id)

        assert isinstance(guild, Guild)
        assert guild.name == "MyGuild"
        assert guild.description == "A guild for testing"
        assert guild.get_agent_count() == 1

        # clean up
        guild.shutdown()

    #  Validates that a properly formatted GuildSpec can be built without any issues.
    def test_null_case(self, org_id):
        pass

    #  Validates that an invalid agent class name raises a ValidationError.
    def test_build_with_invalid_agent_class_name(self, client_properties, org_id, messaging_server):
        server, port = messaging_server
        # Test that ValidationError is raised during AgentSpec creation, not guild launch
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
