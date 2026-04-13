import json

from pydantic import ValidationError
import pytest

from rustic_ai.core import AgentMode, AgentType, SimpleClient
from rustic_ai.core.guild import GSKC
from rustic_ai.core.guild.dsl import AgentSpec, GuildSpec
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name

from core.tests.guild.simple_agent import SimpleAgent


class TestGuildSpec:

    #  create a GuildSpec instance with valid name, description, properties, and agents
    def test_create_guildspec_with_valid_attributes(self, client_properties):
        guild_spec = GuildSpec(
            name="MyGuild",
            description="A guild for testing",
            properties={
                "storage": {
                    "class": "rustic_ai.core.messaging.storage.InMemoryStorage",
                    "properties": {},
                }
            },
            agents=[
                AgentSpec(
                    name="Agent1",
                    description="First agent",
                    class_name=get_qualified_class_name(SimpleAgent),
                    agent_type=AgentType.BOT,
                    mode=AgentMode.REMOTE,
                ),
                AgentSpec(
                    name="Agent2",
                    description="Second agent",
                    class_name=get_qualified_class_name(SimpleAgent),
                    agent_type=AgentType.HUMAN,
                    mode=AgentMode.LOCAL,
                ),
            ],
        )

        guild_spec.set_execution_engine("rustic_ai.core.execution_engine.local.LocalExecutionEngine")
        guild_spec.set_messaging("rustic_ai.core.messaging.backend.in_memory", "InMemoryBackend", {})

        assert guild_spec.name == "MyGuild"
        assert guild_spec.description == "A guild for testing"
        assert len(guild_spec.properties) == 3
        assert len(guild_spec.agents) == 2

        spec_props = guild_spec.properties
        assert spec_props[GSKC.EXECUTION_ENGINE] == "rustic_ai.core.execution_engine.local.LocalExecutionEngine"
        assert spec_props[GSKC.MESSAGING][GSKC.BACKEND_MODULE] == "rustic_ai.core.messaging.backend.in_memory"
        assert spec_props[GSKC.MESSAGING][GSKC.BACKEND_CLASS] == "InMemoryBackend"
        assert spec_props[GSKC.MESSAGING][GSKC.BACKEND_CONFIG] == {}

    #  add an agent to a GuildSpec instance
    def test_add_agent_to_guildspec(self, client_properties):
        guild_spec = GuildSpec(
            name="MyGuild",
            description="A guild for testing",
            properties={
                "storage": {
                    "class": "rustic_ai.core.messaging.storage.InMemoryStorage",
                    "properties": {},
                }
            },
            agents=[],
        )
        agent_spec: AgentSpec = AgentSpec(
            name="Agent1",
            description="First agent",
            class_name=get_qualified_class_name(SimpleAgent),
            agent_type=AgentType.BOT,
            mode=AgentMode.REMOTE,
        )
        guild_spec.add_agent_spec(agent_spec)
        assert len(guild_spec.agents) == 1
        assert guild_spec.agents[0] == agent_spec

    #  add an existing agent to a GuildSpec instance
    def test_add_existing_agent_to_guildspec(self, client_properties):
        guild_spec = GuildSpec(
            name="MyGuild",
            description="A guild for testing",
            properties={
                "storage": {
                    "class": "rustic_ai.core.messaging.storage.InMemoryStorage",
                    "properties": {},
                }
            },
            agents=[],
        )
        agent_spec: AgentSpec = AgentSpec(
            name="Agent1",
            description="First agent",
            class_name=get_qualified_class_name(SimpleAgent),
            agent_type=AgentType.BOT,
            mode=AgentMode.REMOTE,
        )
        guild_spec.add_agent_spec(agent_spec)
        assert len(guild_spec.agents) == 1
        assert guild_spec.agents[0] == agent_spec

        with pytest.raises(ValueError, match=f"Agent {agent_spec.name} already exists in guild"):
            guild_spec.add_agent_spec(agent_spec)

    #  create a GuildSpec instance with empty properties and agents
    def test_create_guildspec_with_empty_properties_and_agents(self, client_properties):
        guild_spec = GuildSpec(
            name="MyGuild",
            description="A guild for testing",
            properties={},
            agents=[],
        )
        assert len(guild_spec.properties) == 0
        assert len(guild_spec.agents) == 0

    #  create a GuildSpec instance with empty name
    def test_create_guildspec_with_empty_name(self, client_properties):
        with pytest.raises(ValidationError):
            GuildSpec(
                name="",
                description="A guild for testing",
                properties={
                    "storage": {
                        "class": "rustic_ai.core.messaging.storage.InMemoryStorage",
                        "properties": {},
                    }
                },
                agents=[
                    AgentSpec(
                        name="Agent1",
                        description="First agent",
                        class_name=get_qualified_class_name(SimpleAgent),
                        agent_type=AgentType.BOT,
                        mode=AgentMode.REMOTE,
                        properties={
                            "data-template": {},
                            "client_class": SimpleClient,
                            "client_properties": client_properties,
                        },
                    ),
                    AgentSpec(
                        name="Agent2",
                        description="Second agent",
                        class_name=get_qualified_class_name(SimpleAgent),
                        agent_type=AgentType.HUMAN,
                        mode=AgentMode.LOCAL,
                        properties={
                            "data-template": {},
                            "client_class": SimpleClient,
                            "client_properties": client_properties,
                        },
                    ),
                ],
            )

    #  create a GuildSpec instance with name exceeding maximum length
    def test_create_guildspec_with_name_exceeding_max_length(self, client_properties):
        with pytest.raises(ValidationError):
            GuildSpec(
                name="ThisIsAVeryLongGuildNameThatExceedsTheMaximumLengthThisIsAVeryLongGuildNameThatExceedsTheMaximumLength",
                description="A guild for testing",
                properties={
                    "storage": {
                        "class": "rustic_ai.core.messaging.storage.InMemoryStorage",
                        "properties": {},
                    }
                },
                agents=[
                    AgentSpec(
                        name="Agent1",
                        description="First agent",
                        class_name=get_qualified_class_name(SimpleAgent),
                        agent_type=AgentType.BOT,
                        mode=AgentMode.REMOTE,
                        properties={
                            "data-template": {},
                            "client_class": SimpleClient,
                            "client_properties": client_properties,
                        },
                    ),
                    AgentSpec(
                        name="Agent2",
                        description="Second agent",
                        class_name=get_qualified_class_name(SimpleAgent),
                        agent_type=AgentType.HUMAN,
                        mode=AgentMode.LOCAL,
                        properties={
                            "data-template": {},
                            "client_class": SimpleClient,
                            "client_properties": client_properties,
                        },
                    ),
                ],
            )

    #  create a GuildSpec instance with empty description
    def test_create_guildspec_with_empty_description(self, client_properties):
        with pytest.raises(ValidationError):
            GuildSpec(
                name="MyGuild",
                description="",
                properties={
                    "storage": {
                        "class": "rustic_ai.core.messaging.storage.InMemoryStorage",
                        "properties": {},
                    }
                },
                agents=[
                    AgentSpec(
                        name="Agent1",
                        description="First agent",
                        class_name=get_qualified_class_name(SimpleAgent),
                        agent_type=AgentType.BOT,
                        mode=AgentMode.REMOTE,
                        properties={
                            "data-template": {},
                            "client_class": SimpleClient,
                            "client_properties": client_properties,
                        },
                    ),
                    AgentSpec(
                        name="Agent2",
                        description="Second agent",
                        class_name=get_qualified_class_name(SimpleAgent),
                        agent_type=AgentType.HUMAN,
                        mode=AgentMode.LOCAL,
                        properties={
                            "data-template": {},
                            "client_class": SimpleClient,
                            "client_properties": client_properties,
                        },
                    ),
                ],
            )

    def test_parse_routes_with_wildcard_agent_type_from_dict(self):
        spec_data = {
            "name": "RoutingGuild",
            "description": "Guild with wildcard route",
            "properties": {},
            "agents": [
                {
                    "name": "Agent1",
                    "description": "First agent",
                    "class_name": get_qualified_class_name(SimpleAgent),
                    "agent_type": AgentType.BOT.value,
                    "mode": AgentMode.REMOTE.value,
                }
            ],
            "routes": {
                "steps": [
                    {
                        "agent_type": "*",
                        "method_name": "handle",
                        "message_format": "generic_json",
                        "destination": {"topics": ["default_topic"]},
                        "route_times": 2,
                        "reason": "route all agent types",
                    }
                ]
            },
        }

        guild_spec = GuildSpec.model_validate(spec_data)

        assert len(guild_spec.routes.steps) == 1
        route = guild_spec.routes.steps[0]
        assert route.agent_type == "*"
        assert route.method_name == "handle"
        assert route.message_format == "generic_json"
        assert route.destination is not None
        assert route.destination.topics == ["default_topic"]
        assert route.route_times == 2
        assert route.reason == "route all agent types"

    def test_parse_routes_with_wildcard_agent_type_from_json(self):
        spec_data = {
            "name": "RoutingGuildJson",
            "description": "Guild parsed from json",
            "properties": {},
            "agents": [
                {
                    "name": "Agent1",
                    "description": "First agent",
                    "class_name": get_qualified_class_name(SimpleAgent),
                    "agent_type": AgentType.BOT.value,
                    "mode": AgentMode.REMOTE.value,
                }
            ],
            "routes": {
                "steps": [
                    {
                        "agent_type": "rustic_ai.core.agents.*",
                        "method_name": "process",
                        "message_format": "generic_json",
                        "destination": {"topics": "topic_a"},
                    },
                    {
                        "agent_type": "*GatewayAgent",
                        "method_name": "returned",
                        "message_format": "generic_json",
                        "destination": {"topics": ["topic_b", "topic_c"]},
                    },
                ]
            },
        }

        guild_spec = GuildSpec.model_validate_json(json.dumps(spec_data))

        assert len(guild_spec.routes.steps) == 2

        first = guild_spec.routes.steps[0]
        assert first.agent_type == "rustic_ai.core.agents.*"
        assert first.destination is not None
        assert first.destination.topics == "topic_a"

        second = guild_spec.routes.steps[1]
        assert second.agent_type == "*GatewayAgent"
        assert second.destination is not None
        assert second.destination.topics == ["topic_b", "topic_c"]
