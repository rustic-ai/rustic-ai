import os
import re

from fastapi.testclient import TestClient
import pytest
from sqlmodel import Session

from rustic_ai.api_server.catalog.models import (
    CatalogAgentEntry,
    LaunchGuildFromBlueprintRequest,
)
from rustic_ai.core.guild.metastore import Metastore


@pytest.fixture
def catalog_engine(request):
    # Generate unique database filename based on test name and worker
    test_name = request.node.name
    worker_id = os.environ.get("PYTEST_XDIST_WORKER", "master")

    # Sanitize test name for filename
    sanitized_test_name = re.sub(r"[^\w\-_.]", "_", test_name)
    db_filename = f"catalog_api_test_{sanitized_test_name}_{worker_id}.db"
    db_url = f"sqlite:///{db_filename}"

    Metastore.drop_db(unsafe=True)
    Metastore.initialize_engine(db_url)
    yield Metastore.get_engine()
    Metastore.drop_db(unsafe=True)

    # Clean up database file
    try:
        os.remove(db_filename)
    except FileNotFoundError:
        pass


@pytest.fixture
def catalog_client(catalog_engine):
    from rustic_ai.api_server.main import app

    return TestClient(app)


@pytest.fixture
def session(catalog_engine):
    with Session(catalog_engine) as session:
        yield session


simple_agent_with_props_schema = {
    "agent_name": "SimpleAgentWithProps",
    "qualified_class_name": "rustic_ai.testing.agents.simple_agent.SimpleAgentWithProps",
    "agent_doc": "No documentation written for Agent",
    "agent_props_schema": {
        "properties": {"prop1": {"title": "Prop1", "type": "string"}, "prop2": {"title": "Prop2", "type": "integer"}},
        "required": ["prop1", "prop2"],
        "title": "SimpleAgentProps",
        "type": "object",
    },
    "message_handlers": {
        "collect_message": {
            "handler_name": "collect_message",
            "message_format": "generic_json",
            "message_format_schema": {"type": "object"},
            "handler_doc": None,
            "send_message_calls": [],
        }
    },
    "agent_dependencies": {},
}


def test_create_blueprint_vars(catalog_client, session: Session):
    simple_agent_entry = CatalogAgentEntry(**simple_agent_with_props_schema)
    session.add(simple_agent_entry)
    session.commit()
    # Create a blueprint with a valid GuildSpec
    user_id = "b145c434-28a8-4393-885b-716494700249"
    org_id = "e3602047-7e30-4504-ab2d-b081ff227494"
    spec = {
        "name": "test_guild_name",
        "description": "description for test_guild_name",
        "configuration_schema": {
            "type": "object",
            "properties": {
                "agent1": {"type": "string"},
                "model_id": {"type": "string"},
                "model_version": {"type": "number"},
            },
        },
        "configuration": {"agent1": "asdf", "model_id": "custom/model_1", "model_version": 2},
        "agents": [
            {
                "name": "{{ agent1 }}",
                "description": "A simple agent with variable properties",
                "class_name": "rustic_ai.testing.agents.simple_agent.SimpleAgentWithProps",
                "additional_topics": [],
                "properties": {"prop1": "{{ model_id }}", "prop2": "{{ model_version }}"},
            }
        ],
        "routes": {
            "steps": [
                {
                    "agent": {"name": "{{ agent1 }}"},
                    "origin_filter": {"origin_message_format": "__main__.FilteringMessage"},
                }
            ]
        },
    }
    blueprint_data = {
        "name": "qwerty",
        "description": "Test Blueprint with variables in guildSpec",
        "exposure": "private",
        "author_id": user_id,
        "organization_id": org_id,
        "version": "1.0.0",
        "category_id": None,
        "spec": spec,
    }

    response = catalog_client.post("/catalog/blueprints/", json=blueprint_data)
    assert response.status_code == 201
    blueprint_id = response.json()["id"]

    # Ensure stored spec matches exactly with the given input
    stored_bp_response = catalog_client.get(f"/catalog/blueprints/{blueprint_id}")
    assert stored_bp_response.status_code == 200
    stored_bp = stored_bp_response.json()
    assert stored_bp["spec"] == spec

    # Test successful guild launch
    launch_request = LaunchGuildFromBlueprintRequest(
        guild_name="My New Guild",
        user_id=user_id,
        org_id=org_id,
        description="A custom guild description",
    )

    launch_response = catalog_client.post(
        f"/catalog/blueprints/{blueprint_id}/guilds",
        json=launch_request.model_dump(),
        headers={"Content-Type": "application/json"},
    )

    assert launch_response.status_code == 201

    # Test successful guild launch with config
    launch_request_vars = LaunchGuildFromBlueprintRequest(
        guild_name="My New Guild",
        user_id=user_id,
        org_id=org_id,
        description="A custom guild description",
        configuration={"agent1": "007", "model_id": "custom/secret_model", "model_version": 3},
    )

    launch_response = catalog_client.post(
        f"/catalog/blueprints/{blueprint_id}/guilds",
        json=launch_request_vars.model_dump(),
        headers={"Content-Type": "application/json"},
    )

    assert launch_response.status_code == 201

    # Test guild launch with invalid config
    launch_invalid_vars = LaunchGuildFromBlueprintRequest(
        guild_name="My New Guild",
        user_id=user_id,
        org_id=org_id,
        description="A custom guild description",
        configuration={"agent1": 7, "model_id": "custom/secret_model", "model_version": 3},
    )

    launch_response = catalog_client.post(
        f"/catalog/blueprints/{blueprint_id}/guilds",
        json=launch_invalid_vars.model_dump(),
        headers={"Content-Type": "application/json"},
    )

    assert launch_response.status_code == 400
