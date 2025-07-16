import os
import re

from fastapi.testclient import TestClient
import pytest
from sqlmodel import Session

from rustic_ai.api_server.catalog.models import CatalogAgentEntry
from rustic_ai.core.guild.metastore.database import Metastore


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


scrapper_agent_data = {
    "agent_name": "PlaywrightScrapperAgent",
    "qualified_class_name": "tools.webscrape_playwright.playwright_agent.PlaywrightScrapperAgent",
    "agent_doc": "No documentation written for Agent",
    "agent_props_schema": {
        "description": "Empty class for Agent properties.",
        "properties": {},
        "title": "BaseAgentProps",
        "type": "object",
    },
    "message_handlers": {
        "scrape": {
            "handler_name": "scrape",
            "message_format": "tools.webscrape_playwright.playwright_agent.WebScrappingRequest",
            "message_format_schema": {
                "$defs": {
                    "JsonValue": {},
                    "MediaLink": {
                        "properties": {
                            "id": {"title": "Id", "type": "string"},
                            "name": {
                                "anyOf": [{"type": "string"}, {"type": "null"}],
                                "default": None,
                                "title": "Name",
                            },
                            "metadata": {
                                "anyOf": [
                                    {"additionalProperties": {"$ref": "#/$defs/JsonValue"}, "type": "object"},
                                    {"type": "null"},
                                ],
                                "default": {},
                                "title": "Metadata",
                            },
                            "url": {"title": "Url", "type": "string"},
                            "mimetype": {
                                "anyOf": [{"type": "string"}, {"type": "null"}],
                                "default": None,
                                "title": "Mimetype",
                            },
                            "encoding": {
                                "anyOf": [{"type": "string"}, {"type": "null"}],
                                "default": None,
                                "title": "Encoding",
                            },
                            "on_filesystem": {
                                "anyOf": [{"type": "boolean"}, {"type": "null"}],
                                "default": None,
                                "title": "On Filesystem",
                            },
                        },
                        "required": ["url"],
                        "title": "MediaLink",
                        "type": "object",
                    },
                },
                "properties": {
                    "id": {"title": "ID of the request", "type": "string"},
                    "links": {"items": {"$ref": "#/$defs/MediaLink"}, "title": "URL to scrape", "type": "array"},
                },
                "required": ["links"],
                "title": "WebScrappingRequest",
                "type": "object",
            },
            "handler_doc": None,
            "send_message_calls": [],
        }
    },
    "agent_dependencies": {
        "filesystem": {
            "dependency_key": "filesystem",
            "dependency_var": None,
            "guild_level": True,
            "agent_level": False,
            "variable_name": "filesystem",
        }
    },
}


@pytest.fixture
def setup_data(session: Session):
    # Prepare agent data
    echo_agent = {
        "agent_name": "EchoAgent",
        "qualified_class_name": "rustic_ai.agents.utils.echo_agent.EchoAgent",
        "agent_doc": "An Agent that echoes the received message back to the sender.",
        "agent_props_schema": {
            "description": "Empty class for Agent properties.",
            "properties": {},
            "title": "BaseAgentProps",
            "type": "object",
        },
        "message_handlers": {
            "echo_message": {
                "handler_name": "echo_message",
                "message_format": "generic_json",
                "message_format_schema": {"type": "object"},
                "handler_doc": None,
                "send_message_calls": [
                    {
                        "calling_class": "EchoAgent",
                        "calling_function": "echo_message",
                        "call_type": "send_dict",
                        "message_type": "ctx.format",
                    }
                ],
            }
        },
        "agent_dependencies": {},
    }

    echo_agent_entry = CatalogAgentEntry(**echo_agent)

    # Create scrapper_agent in the session context
    scrapper_agent_entry = CatalogAgentEntry.model_validate(scrapper_agent_data)

    session.add(echo_agent_entry)
    session.add(scrapper_agent_entry)
    session.commit()

    # Return both agents so tests can access them
    return echo_agent_entry, scrapper_agent_entry


def test_register_agent(catalog_client):
    agent_data = {
        "agent_name": "TestAgent",
        "qualified_class_name": "rustic_ai.agents.test.TestAgent",
        "agent_doc": "A test agent for API testing",
        "agent_props_schema": {
            "description": "Test agent properties",
            "properties": {},
            "title": "TestAgentProps",
            "type": "object",
        },
        "message_handlers": {
            "test_message": {
                "handler_name": "test_message",
                "message_format": "generic_json",
                "message_format_schema": {"type": "object"},
                "handler_doc": "Test message handler",
                "send_message_calls": [],
            }
        },
        # Define agent_dependencies as an array of objects for the request
        "agent_dependencies": [
            {
                "dependency_key": "filesystem",
                "dependency_var": None,
                "guild_level": True,
                "agent_level": False,
                "variable_name": "filesystem",
            }
        ],
    }

    response = catalog_client.post("/catalog/agents", json=agent_data)

    assert response.status_code == 201, f"Expected status code 201, got {response.status_code}"

    get_response = catalog_client.get(f"/catalog/agents?class_names={agent_data['qualified_class_name']}")
    assert get_response.status_code == 200

    created_agent = get_response.json()[agent_data["qualified_class_name"]]
    assert created_agent["agent_name"] == agent_data["agent_name"]
    assert created_agent["qualified_class_name"] == agent_data["qualified_class_name"]

    dependencies_output = created_agent["agent_dependencies"][0]
    dependencies_input = agent_data["agent_dependencies"][0]  # type: ignore

    assert dependencies_output == dependencies_input


def test_fetch_agent_by_name(catalog_client, setup_data):
    response = catalog_client.get("/catalog/agents/rustic_ai.agents.utils.echo_agent.EchoAgent")
    assert response.status_code == 200

    agent = response.json()
    assert agent["agent_name"] == "EchoAgent"
    assert agent["qualified_class_name"] == "rustic_ai.agents.utils.echo_agent.EchoAgent"


def test_agent_listing(catalog_client, setup_data):
    response = catalog_client.get("/catalog/agents")
    assert response.status_code == 200
    all_agents = response.json()
    assert len(all_agents) > 0
    assert "rustic_ai.agents.utils.echo_agent.EchoAgent" in response.json()
    assert "tools.webscrape_playwright.playwright_agent.PlaywrightScrapperAgent" in response.json()


def test_agent_listing_with_class_name(catalog_client, setup_data):
    response = catalog_client.get("/catalog/agents?class_names=rustic_ai.agents.utils.echo_agent.EchoAgent")
    assert response.status_code == 200
    all_agents = response.json()
    assert len(all_agents) > 0
    assert "rustic_ai.agents.utils.echo_agent.EchoAgent" in response.json()
    assert "tools.webscrape_playwright.playwright_agent.PlaywrightScrapperAgent" not in response.json()


def test_fetch_message_schema(catalog_client, setup_data):
    echo_agent, scrapper_agent = setup_data
    scrape_handler = scrapper_agent.message_handlers["scrape"]
    request_format = scrape_handler["message_format"]  # type: ignore
    response1 = catalog_client.get(f"/catalog/agents/message_schema/?message_format={request_format}")
    assert response1.status_code == 200
    assert response1.json() == scrape_handler["message_format_schema"]  # type: ignore
    invalid_class = "SOME_INVALID_CLASS"
    response2 = catalog_client.get(f"/catalog/agents/message_schema/?message_format={invalid_class}")
    assert response2.status_code == 404
    response5 = catalog_client.get("/catalog/agents/message_schema/")
    assert response5.status_code == 422
    error = response5.json()
    error_detail = error["detail"]
    assert error_detail[0] == {
        "msg": "Field required",
        "type": "missing",
        "loc": ["query", "message_format"],
        "input": None,
    }
