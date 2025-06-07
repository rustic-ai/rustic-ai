import json

from rustic_ai.api_server.guilds.schema import LaunchGuildReq
from rustic_ai.core.agents.testutils import EchoAgent
from rustic_ai.core.guild.builders import AgentBuilder
from rustic_ai.core.guild.dsl import AgentSpec, GuildSpec


def test_create_guild(client, org_id):
    agent1: AgentSpec = AgentBuilder(EchoAgent).set_name("Agent1").set_description("First agent").build_spec()

    guild_spec = GuildSpec(
        name="MyGuild",
        description="A guild for testing",
        properties={
            "storage": {
                "class": "rustic_ai.core.messaging.storage.InMemoryStorage",
                "properties": {},
            }
        },
        agents=[agent1],
    )
    req = LaunchGuildReq(spec=guild_spec, org_id=org_id)
    json_data = req.model_dump_json()
    data = json.loads(json_data)

    # Act
    response = client.post("/api/guilds", json=data, headers={"Content-Type": "application/json"})

    # Assert
    assert response.status_code == 201
    assert "id" in response.json()


def test_create_guild_invalid_input(client):
    # Act
    response = client.post("/api/guilds")

    # Assert
    assert response.status_code == 422


def test_create_guild_without_agents(client, org_id):
    # Arrange
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
    req = LaunchGuildReq(spec=guild_spec, org_id=org_id)
    json_data = req.model_dump_json()
    data = json.loads(json_data)

    # Act
    response = client.post("/api/guilds", json=data, headers={"Content-Type": "application/json"})

    # Assert
    assert response.status_code == 201
    assert "id" in response.json()
