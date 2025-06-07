import json

from rustic_ai.api_server.guilds.schema import LaunchGuildReq
from rustic_ai.core.agents.testutils import EchoAgent
from rustic_ai.core.guild.builders import AgentBuilder
from rustic_ai.core.guild.dsl import AgentSpec, GuildSpec


def test_valid_guild_id(client, org_id):
    # Arrange
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
    post_response = client.post("/api/guilds", json=data, headers={"Content-Type": "application/json"})

    assert post_response.status_code == 201
    assert "id" in post_response.json()

    id = post_response.json()["id"]

    # Act
    get_response = client.get(f"/api/guilds/{id}")

    # Assert
    assert get_response.status_code == 200
    assert "name" in get_response.json()


# Raises an HTTPException with status code 404 when an invalid guild_id is provided
def test_invalid_guild_id(client):
    # Act
    response = client.get("/api/guilds/invalid_guild_id")

    # Assert
    assert response.status_code == 404
    assert response.json()["detail"] == "Guild not found"
