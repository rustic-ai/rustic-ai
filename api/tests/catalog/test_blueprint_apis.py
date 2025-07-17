import os
import re

from fastapi.testclient import TestClient
import pytest
from sqlmodel import Session

from rustic_ai.api_server.catalog.catalog_store import CatalogStore
from rustic_ai.api_server.catalog.models import (
    AgentNameWithIcon,
    BlueprintAgentsIconReqRes,
    BlueprintCategoryCreate,
    BlueprintCategoryResponse,
    BlueprintCreate,
    BlueprintReviewCreate,
    CatalogAgentEntry,
    LaunchGuildFromBlueprintRequest,
)
from rustic_ai.api_server.guilds.schema import LaunchGuildReq
from rustic_ai.core.agents.testutils import EchoAgent
from rustic_ai.core.guild.dsl import GuildSpec
from rustic_ai.core.guild.metastore.database import Metastore
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name

from rustic_ai.testing.agents.sample_agents import DemoAgentSimple, MessageDataType
from rustic_ai.testing.agents.simple_agent import SimpleAgent


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
def catalog_store(catalog_engine):
    return CatalogStore(catalog_engine)


@pytest.fixture
def session(catalog_engine):
    with Session(catalog_engine) as session:
        yield session


echo_agent = {
    "agent_name": "EchoAgent",
    "qualified_class_name": "rustic_ai.core.agents.testutils.echo_agent.EchoAgent",
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

simple_agent = {
    "agent_name": "SimpleAgent",
    "qualified_class_name": SimpleAgent.get_qualified_class_name(),
    "agent_doc": "No documentation written for Agent",
    "agent_props_schema": {
        "description": "Empty class for Agent properties.",
        "properties": {},
        "title": "BaseAgentProps",
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

demo_agent = {
    "agent_name": "DemoAgentSimple",
    "qualified_class_name": DemoAgentSimple.get_qualified_class_name(),
    "agent_doc": "No documentation written for Agent",
    "agent_props_schema": {
        "description": "Empty class for Agent properties.",
        "properties": {},
        "title": "BaseAgentProps",
        "type": "object",
    },
    "message_handlers": {
        "handle_message": {
            "handler_name": "handle_message",
            "message_format": get_qualified_class_name(MessageDataType),
            "message_format_schema": {
                "properties": {"data": {"title": "Data", "type": "string"}},
                "required": ["data"],
                "title": "MessageDataType",
                "type": "object",
            },
            "handler_doc": None,
            "send_message_calls": [],
        }
    },
    "agent_dependencies": {},
}


@pytest.fixture
def setup_data(catalog_store: CatalogStore, session: Session):
    user_id = "b145c434-28a8-4393-885b-716494700249"
    org_id = "e3602047-7e30-4504-ab2d-b081ff227494"

    category_create = BlueprintCategoryCreate(name="finance", description="Finance related blueprints")
    category_id = catalog_store.create_category(category_create)
    category = BlueprintCategoryResponse(**category_create.model_dump(), id=category_id)

    blueprint_create = BlueprintCreate(
        name="Test Blueprint",
        description="A test blueprint",
        exposure="private",
        author_id=user_id,
        organization_id=org_id,
        version="1.0.0",
        spec={"name": "test blueprint spec", "description": "a guildspec for testing blueprint api"},
        category_id=category_id,
        icon="icon.png",
    )
    blueprint_id = catalog_store.create_blueprint(blueprint_create)
    blueprint = catalog_store.get_blueprint(blueprint_id)

    blueprint_review_create = BlueprintReviewCreate(user_id=user_id, rating=4, review="A good blueprint")
    review = catalog_store.create_blueprint_review(blueprint_id, blueprint_review_create)

    org2_id = "asdfjkl"

    echo_agent_entry = CatalogAgentEntry(**echo_agent)
    simple_agent_entry = CatalogAgentEntry(**simple_agent)
    demo_agent_entry = CatalogAgentEntry(**demo_agent)

    session.add(echo_agent_entry)
    session.add(simple_agent_entry)
    session.add(demo_agent_entry)

    session.commit()
    return {
        "user_id": user_id,
        "organization_id": org_id,
        "category": category,
        "blueprint": blueprint,
        "review": review,
        "org2_id": org2_id,
    }


def test_create_blueprint(setup_data, catalog_client):
    blueprint_data = {
        "name": "New Blueprint",
        "description": "A new blueprint",
        "exposure": "private",
        "author_id": setup_data["user_id"],
        "organization_id": setup_data["organization_id"],
        "version": "1.0.1",
        "spec": {"name": "test create blueprint", "description": "a guildspec for testing blueprint create api"},
        "category_id": setup_data["category"].id,
        "icon": "icon.png",
    }
    blueprint_create = BlueprintCreate.model_validate(blueprint_data)
    response = catalog_client.post("/catalog/blueprints/", json=blueprint_create.model_dump())
    assert response.status_code == 201


def test_get_blueprint(setup_data, catalog_client):
    blueprint_id = setup_data["blueprint"].id
    response = catalog_client.get(f"/catalog/blueprints/{blueprint_id}")
    assert response.status_code == 200
    assert response.json()["id"] == blueprint_id


def test_create_blueprint_with_list_tags(setup_data, catalog_client):
    blueprint_data = {
        "name": "BlueprintWithTags",
        "description": "blueprint with tags, starter_prompts, commands, intro_msg ",
        "exposure": "private",
        "author_id": setup_data["user_id"],
        "organization_id": setup_data["organization_id"],
        "version": "1.0.1",
        "spec": {"name": "blueprint spec 2", "description": "a guildspec for testing blueprint create api"},
        "category_id": setup_data["category"].id,
        "icon": "icon.png",
        "tags": ["testing", "validation", "qa"],
        "commands": ["/start", "/stop"],
        "starter_prompts": ["what is a blueprint?", "what are the different types of agents?"],
        "intro_msg": "This is a sample guild. you can use the commands `/start` and `/stop`",
    }
    blueprint_create = BlueprintCreate.model_validate(blueprint_data)
    response = catalog_client.post("/catalog/blueprints/", json=blueprint_create.model_dump())
    assert response.status_code == 201
    blueprint_id = response.json()["id"]
    blueprint_response = catalog_client.get(f"/catalog/blueprints/{blueprint_id}")
    assert blueprint_response.status_code == 200
    assert response.json()["id"] == blueprint_id
    blueprint_details = blueprint_response.json()
    missing_tags = [item for item in blueprint_data["tags"] if item not in blueprint_details["tags"]]
    if missing_tags:
        pytest.fail(f"Missing tags in actual data: {missing_tags}")
    missing_prompts = [
        item for item in blueprint_data["starter_prompts"] if item not in blueprint_details["starter_prompts"]
    ]
    if missing_prompts:
        pytest.fail(f"Missing prompts in actual data: {missing_prompts}")
    missing_commands = [item for item in blueprint_data["commands"] if item not in blueprint_details["commands"]]
    if missing_commands:
        pytest.fail(f"Missing commands in actual data: {missing_commands}")
    tags_response = catalog_client.get("/catalog/tags/")
    assert tags_response.status_code == 200
    assert len(tags_response.json()) >= len(blueprint_data["tags"])
    missing_tags = [item for item in blueprint_data["tags"] if item not in tags_response.json()]
    if missing_tags:
        pytest.fail(f"Missing tags in list response: {missing_tags}")


def test_create_review(setup_data, catalog_client):
    review_data = {
        "blueprint_id": setup_data["blueprint"].id,
        "rating": 5,
        "review": "Excellent blueprint",
        "user_id": setup_data["user_id"],
    }
    response = catalog_client.post(f"/catalog/blueprints/{setup_data['blueprint'].id}/reviews/", json=review_data)
    assert response.status_code == 201


def test_get_blueprint_reviews(setup_data, catalog_client):
    blueprint_id = setup_data["blueprint"].id
    response = catalog_client.get(f"/catalog/blueprints/{blueprint_id}/reviews/")
    assert response.status_code == 200
    assert len(response.json()["reviews"]) > 0


def test_get_category_blueprints(setup_data, catalog_client):
    category_name = setup_data["category"].name
    response = catalog_client.get(f"/catalog/categories/{category_name}/blueprints/")
    assert response.status_code == 200
    assert len(response.json()) > 0

    category_list_res = catalog_client.get("/catalog/categories/")
    assert category_list_res.status_code == 200
    assert len(category_list_res.json()) > 0
    category0 = category_list_res.json()[0]
    assert category0["name"] == category_name


def test_get_user_accessible_blueprints(setup_data, catalog_client):
    user_id = setup_data["user_id"]
    response = catalog_client.get(f"/catalog/users/{user_id}/blueprints/accessible/")
    assert response.status_code == 200
    assert len(response.json()) > 0


def test_share_blueprint_with_organization(setup_data, catalog_client):
    blueprint_id = setup_data["blueprint"].id
    org2 = setup_data["org2_id"]
    response = catalog_client.post(f"/catalog/blueprints/{blueprint_id}/share/", json={"organization_id": org2})
    assert response.status_code == 204

    response = catalog_client.delete(f"/catalog/blueprints/{blueprint_id}/share/{org2}")
    assert response.status_code == 204


def test_blueprint_guild_linking(setup_data, catalog_client, org_id):
    guild_spec = GuildSpec(
        name="MyGuild",
        description="A guild for testing",
        properties={"storage": {"class": "rustic_ai.messaging.storage.InMemoryStorage", "properties": {}}},
        agents=[],
    )
    req = LaunchGuildReq(spec=guild_spec, org_id=org_id)
    response = catalog_client.post(
        "/api/guilds",
        json=req.model_dump(),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 201
    assert "id" in response.json()
    guild_id = response.json()["id"]
    # Test when guild is not linked to any blueprint
    guild_blueprint = catalog_client.get(f"/catalog/guilds/{guild_id}/blueprints/")
    assert guild_blueprint.status_code == 404
    assert guild_blueprint.json()["detail"] == f"No Blueprint associated with guild {guild_id}"
    # Test linking guild to a blueprint
    blueprint_id = setup_data["blueprint"].id
    response = catalog_client.post(f"/catalog/blueprints/{blueprint_id}/guilds/{guild_id}")
    assert response.status_code == 204
    # Test getting blueprint for guild
    blueprint_resp = catalog_client.get(f"/catalog/guilds/{guild_id}/blueprints/")
    assert blueprint_resp.status_code == 200
    assert blueprint_resp.json()["id"] == blueprint_id
    # Test for non-existent guild
    response = catalog_client.get("/catalog/guilds/non-existent/blueprints/")
    assert response.status_code == 404
    response = catalog_client.post(f"/catalog/blueprints/{blueprint_id}/guilds/non-existent")
    assert response.status_code == 404
    assert response.json()["detail"] == "Guild non-existent not found"
    # Test for non-existent blueprint
    response = catalog_client.post("/catalog/blueprints/na/guilds/non-existent")
    assert response.status_code == 404
    assert response.json()["detail"] == "Blueprint na not found"


def test_add_user_to_guild(setup_data, catalog_client, org_id):
    guild_spec = GuildSpec(
        name="UserGuild ",
        description="A guild for testing",
        properties={"storage": {"class": "rustic_ai.messaging.storage.InMemoryStorage", "properties": {}}},
        agents=[],
    )
    req = LaunchGuildReq(spec=guild_spec, org_id=org_id)
    response = catalog_client.post(
        "/api/guilds",
        json=req.model_dump(),
        headers={"Content-Type": "application/json"},
    )
    guild_id = response.json()["id"]
    # Test when user is not linked to a guild
    user_id = setup_data["user_id"]
    user_guilds_res = catalog_client.get(f"/catalog/users/{user_id}/guilds/")
    assert user_guilds_res.status_code == 200
    assert len(user_guilds_res.json()) == 0
    # Test adding user to guild
    response = catalog_client.post(f"/catalog/guilds/{guild_id}/users/{user_id}")
    assert response.status_code == 204
    user_guilds_res = catalog_client.get(f"/catalog/users/{user_id}/guilds/")
    assert user_guilds_res.status_code == 200
    assert len(user_guilds_res.json()) == 1
    guild_res = user_guilds_res.json()[0]
    assert guild_res["id"] == guild_id
    assert guild_res["name"] == guild_spec.name
    assert guild_res["blueprint_id"] is None
    delete_response = catalog_client.delete(f"/catalog/guilds/{guild_id}/users/{user_id}")
    assert delete_response.status_code == 204


def test_user_guild_response(setup_data, catalog_client, org_id):
    guild_spec = GuildSpec(
        name="UserGuild ",
        description="A guild for testing",
        properties={"storage": {"class": "rustic_ai.messaging.storage.InMemoryStorage", "properties": {}}},
        agents=[],
    )
    req = LaunchGuildReq(spec=guild_spec, org_id=org_id)
    response = catalog_client.post(
        "/api/guilds",
        json=req.model_dump(),
        headers={"Content-Type": "application/json"},
    )
    guild_id = response.json()["id"]
    blueprint_id = setup_data["blueprint"].id
    # link blueprint and guild
    catalog_client.post(f"/catalog/blueprints/{blueprint_id}/guilds/{guild_id}")
    user_id = setup_data["user_id"]
    # add user to guild
    catalog_client.post(f"/catalog/guilds/{guild_id}/users/{user_id}")
    user_guilds_res = catalog_client.get(f"/catalog/users/{user_id}/guilds/")
    assert user_guilds_res.status_code == 200
    assert len(user_guilds_res.json()) == 1
    guild_res = user_guilds_res.json()[0]
    assert guild_res["id"] == guild_id
    assert guild_res["name"] == guild_spec.name
    # check that result includes blueprint_id
    assert guild_res["blueprint_id"] == blueprint_id
    assert guild_res["icon"] == "icon.png"


def test_list_guilds_org(catalog_client):
    org_id = "testorgid"
    guild_spec = GuildSpec(
        name="OrgGuild ",
        description="A guild for testing",
        properties={"storage": {"class": "rustic_ai.messaging.storage.InMemoryStorage", "properties": {}}},
        agents=[],
    )
    req = LaunchGuildReq(spec=guild_spec, org_id=org_id)
    response = catalog_client.post(
        "/api/guilds",
        json=req.model_dump(),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 201
    org_guilds_res = catalog_client.get(f"/catalog/organizations/{org_id}/guilds/")
    assert org_guilds_res.status_code == 200
    assert len(org_guilds_res.json()) == 1


def test_create_bp_valid_spec(setup_data, catalog_client):
    blueprint_data = {
        "name": "BlueprintWithEchoSpec",
        "description": "blueprint with tags, starter_prompts, commands, intro_msg ",
        "exposure": "private",
        "author_id": setup_data["user_id"],
        "organization_id": setup_data["organization_id"],
        "version": "1.0.1",
        "spec": {
            "name": "Echo Guild",
            "description": "A guild that simply echoes the input",
            "properties": {},
            "agents": [
                {
                    "name": "echo_agent_1",
                    "description": "Echo Agent 1",
                    "class_name": "rustic_ai.core.agents.testutils.echo_agent.EchoAgent",
                    "additional_topics": ["echo_topic"],
                    "properties": {},
                    "listen_to_default_topic": False,
                    "act_only_when_tagged": False,
                    "dependency_map": {},
                }
            ],
            "dependency_map": {},
            "routes": {
                "steps": [
                    {
                        "agent_type": "rustic_ai.agents.utils.user_proxy_agent.UserProxyAgent",
                        "method_name": "unwrap_and_forward_message",
                        "destination": {"topic": "echo_topic"},
                        "route_times": 1,
                    },
                    {
                        "agent": {"name": "echo_agent_1"},
                        "destination": {"topic": "user_message_broadcast"},
                        "route_times": 1,
                    },
                ]
            },
        },
        "category_id": setup_data["category"].id,
        "icon": "icon.png",
        "tags": ["testing", "validation", "qa"],
        "commands": ["/start", "/stop"],
        "starter_prompts": ["what is a blueprint?", "what are the different types of agents?"],
        "intro_msg": "This is a sample guild. you can use the commands `/start` and `/stop`",
    }
    blueprint_create = BlueprintCreate.model_validate(blueprint_data)
    response = catalog_client.post("/catalog/blueprints/", json=blueprint_create.model_dump())
    assert response.status_code == 201
    blueprint_id = response.json()["id"]
    assert blueprint_id is not None


def test_create_incorrect_bp_spec(setup_data, catalog_client):
    blueprint_data = {
        "name": "a",
        "description": "a",
        "version": "1",
        "author_id": setup_data["user_id"],
        "organization_id": setup_data["organization_id"],
        "category_id": None,
        "spec": {
            "agents": [
                {
                    "name": "a",
                    "class_name": "rustic_ai.agents.llm.viz.vegalite_agent.VegaLiteAgent",
                    "description": "f",
                    "additional_topics": [],
                    "listen_to_default_topic": True,
                    "dependency_map": {
                        "llm": {
                            "class_name": "rustic_ai.agents.llm.litellm.litellm_dependency.LiteLLMResolver",
                            "properties": "{...}",
                        }
                    },
                }
            ],
            "routes": {"steps": []},
            "dependency_map": {
                "filesystem": {
                    "class_name": "rustic_ai.guild.agent_ext.depends.filesystem.FileSystemResolver",
                    "properties": "{...}",
                }
            },
            "name": "a",
            "description": "a",
        },
        "tags": None,
    }
    response = catalog_client.post("/catalog/blueprints/", json=blueprint_data)
    assert response.status_code == 422


def test_agent_icons(setup_data, catalog_client, catalog_store):
    bp_data = BlueprintCreate(
        name="test icon",
        version="1.0.0",
        description="bp to test agent icon",
        author_id=setup_data["user_id"],
        organization_id=setup_data["organization_id"],
        category_id=None,
        spec={
            "name": "guild with agent icons",
            "description": "a guild with agent icons",
            "agents": [
                {
                    "name": "echo_agent",
                    "description": "Echo Agent",
                    "class_name": EchoAgent.get_qualified_class_name(),
                },
                {"name": "agent1", "description": "Agent 1", "class_name": SimpleAgent.get_qualified_class_name()},
                {"name": "agent2", "description": "Agent 2", "class_name": DemoAgentSimple.get_qualified_class_name()},
            ],
        },
    )

    response = catalog_client.post(
        "/catalog/blueprints/", json=bp_data.model_dump(), headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 201
    bp_id = response.json()["id"]
    add_icon_response_1 = catalog_client.post(
        f"/catalog/blueprints/{bp_id}/icons/",
        json=BlueprintAgentsIconReqRes(agent_icons=[]).model_dump(),
        headers={"Content-Type": "application/json"},
    )
    assert add_icon_response_1.status_code == 400
    assert add_icon_response_1.json()["detail"] == "No agent icons provided"
    invalid_icons = [
        AgentNameWithIcon(agent_name="non-existent", icon="non-existent.png"),
        AgentNameWithIcon(agent_name="agent1", icon="non-existent.png"),
    ]
    add_icon_response_2 = catalog_client.post(
        f"/catalog/blueprints/{bp_id}/icons/",
        json=BlueprintAgentsIconReqRes(agent_icons=invalid_icons).model_dump(),
        headers={"Content-Type": "application/json"},
    )
    assert add_icon_response_2.status_code == 400
    assert (
        add_icon_response_2.json()["detail"]
        == "Provided agent names are not a subset of the agent names in the blueprint"
    )
    valid_icons = [
        AgentNameWithIcon(
            agent_name="agent1", icon="https://github.com/vega/logos/blob/master/assets/VG_Color@64.png?raw=true"
        )
    ]
    add_icon_response_3 = catalog_client.post(
        f"/catalog/blueprints/{bp_id}/icons/",
        json=BlueprintAgentsIconReqRes(agent_icons=valid_icons).model_dump(),
        headers={"Content-Type": "application/json"},
    )
    assert add_icon_response_3.status_code == 204
    bp_icons_response = catalog_client.get(f"/catalog/blueprints/{bp_id}/icons/")
    assert bp_icons_response.status_code == 200
    icons_response = bp_icons_response.json()["agent_icons"]
    assert len(icons_response) == 1
    # add default icon for pandas
    catalog_store.add_agent_icon(
        DemoAgentSimple.get_qualified_class_name(), "https://pandas.pydata.org/static/img/pandas_mark.svg"
    )
    bp_icons_response_2 = catalog_client.get(f"/catalog/blueprints/{bp_id}/icons/")
    assert bp_icons_response_2.status_code == 200
    icons_response_2 = bp_icons_response_2.json()["agent_icons"]
    assert len(icons_response_2) == 2
    add_icon_response_4 = catalog_client.post(
        f"/catalog/blueprints/{bp_id}/icons/echo_agent",
        json={"agent_icon": "icon.png"},
        headers={"Content-Type": "application/json"},
    )
    assert add_icon_response_4.status_code == 204
    update_icon_response = catalog_client.post(
        f"/catalog/blueprints/{bp_id}/icons/echo_agent",
        json={"agent_icon": "test.png"},
        headers={"Content-Type": "application/json"},
    )
    assert update_icon_response.status_code == 204
    echo_agent_icon_response = catalog_client.get(f"/catalog/blueprints/{bp_id}/icons/echo_agent")
    assert echo_agent_icon_response.status_code == 200
    echo_icon_res = echo_agent_icon_response.json()
    assert echo_icon_res["agent_name"] == "echo_agent"
    assert echo_icon_res["icon"] == "test.png"
    bp_icons_response_3 = catalog_client.get(f"/catalog/blueprints/{bp_id}/icons/")
    assert bp_icons_response_3.status_code == 200
    icons_response_3 = bp_icons_response_3.json()["agent_icons"]
    assert len(icons_response_3) == 3


def test_blueprint_with_duplicate_agent_classes(setup_data, catalog_client):
    blueprint_data = {
        "name": "BlueprintWithEchoSpec",
        "description": "blueprint with tags, starter_prompts, commands, intro_msg ",
        "exposure": "private",
        "author_id": setup_data["user_id"],
        "organization_id": setup_data["organization_id"],
        "version": "1.0.1",
        "spec": {
            "name": "Echo Guild",
            "description": "A guild that simply echoes the input",
            "properties": {},
            "agents": [
                {
                    "name": "echo_agent_1",
                    "description": "Echo Agent 1",
                    "class_name": "rustic_ai.core.agents.testutils.echo_agent.EchoAgent",
                    "additional_topics": ["echo_topic"],
                    "properties": {},
                    "listen_to_default_topic": False,
                    "act_only_when_tagged": False,
                    "dependency_map": {},
                },
                {
                    "name": "echo_agent_2",
                    "description": "Echo Agent 2",
                    "class_name": "rustic_ai.core.agents.testutils.echo_agent.EchoAgent",
                    "additional_topics": ["echo_topic"],
                    "properties": {},
                    "listen_to_default_topic": False,
                    "act_only_when_tagged": False,
                    "dependency_map": {},
                },
            ],
            "dependency_map": {},
            "routes": {
                "steps": [
                    {
                        "agent_type": "rustic_ai.agents.utils.user_proxy_agent.UserProxyAgent",
                        "method_name": "unwrap_and_forward_message",
                        "destination": {"topic": "echo_topic"},
                        "route_times": 1,
                    },
                    {
                        "agent": {"name": "echo_agent_1"},
                        "destination": {"topic": "user_message_broadcast"},
                        "route_times": 1,
                    },
                ]
            },
        },
        "category_id": setup_data["category"].id,
        "icon": "icon.png",
        "tags": ["testing", "validation", "qa"],
    }
    blueprint_create = BlueprintCreate.model_validate(blueprint_data)
    response = catalog_client.post("/catalog/blueprints/", json=blueprint_create.model_dump())
    assert response.status_code == 201
    blueprint_id = response.json()["id"]
    assert blueprint_id is not None


def test_create_blueprints_with_same_agent(setup_data, catalog_client):
    blueprint_data_1 = {
        "name": "Blueprint1WithEchoSpec",
        "description": "blueprint with tags, starter_prompts, commands, intro_msg ",
        "exposure": "private",
        "author_id": setup_data["user_id"],
        "organization_id": setup_data["organization_id"],
        "version": "1.0.1",
        "spec": {
            "name": "Echo Guild",
            "description": "A guild that simply echoes the input",
            "properties": {},
            "agents": [
                {
                    "name": "echo_agent_1",
                    "description": "Echo Agent 1",
                    "class_name": "rustic_ai.core.agents.testutils.echo_agent.EchoAgent",
                    "additional_topics": ["echo_topic"],
                    "properties": {},
                    "listen_to_default_topic": False,
                    "act_only_when_tagged": False,
                    "dependency_map": {},
                },
            ],
            "dependency_map": {},
            "routes": {
                "steps": [
                    {
                        "agent_type": "rustic_ai.agents.utils.user_proxy_agent.UserProxyAgent",
                        "method_name": "unwrap_and_forward_message",
                        "destination": {"topic": "echo_topic"},
                        "route_times": 1,
                    },
                    {
                        "agent": {"name": "echo_agent_1"},
                        "destination": {"topic": "user_message_broadcast"},
                        "route_times": 1,
                    },
                ]
            },
        },
        "category_id": setup_data["category"].id,
        "icon": "icon.png",
        "tags": ["testing", "validation", "qa"],
    }

    blueprint_data_2 = {
        "name": "Blueprint2WithEchoSpec",
        "description": "blueprint with tags, starter_prompts, commands, intro_msg ",
        "exposure": "private",
        "author_id": setup_data["user_id"],
        "organization_id": setup_data["organization_id"],
        "version": "1.0.1",
        "spec": {
            "name": "Echo Guild",
            "description": "A guild that simply echoes the input",
            "properties": {},
            "agents": [
                {
                    "name": "echo_agent_1",
                    "description": "Echo Agent 1",
                    "class_name": "rustic_ai.core.agents.testutils.echo_agent.EchoAgent",
                    "additional_topics": ["echo_topic"],
                    "properties": {},
                    "listen_to_default_topic": False,
                    "act_only_when_tagged": False,
                    "dependency_map": {},
                },
            ],
            "dependency_map": {},
            "routes": {
                "steps": [
                    {
                        "agent_type": "rustic_ai.agents.utils.user_proxy_agent.UserProxyAgent",
                        "method_name": "unwrap_and_forward_message",
                        "destination": {"topic": "echo_topic"},
                        "route_times": 1,
                    },
                    {
                        "agent": {"name": "echo_agent_1"},
                        "destination": {"topic": "user_message_broadcast"},
                        "route_times": 1,
                    },
                ]
            },
        },
        "category_id": setup_data["category"].id,
        "icon": "icon.png",
        "tags": ["testing", "validation", "qa"],
    }
    blueprint_1_create = BlueprintCreate.model_validate(blueprint_data_1)
    response_1 = catalog_client.post("/catalog/blueprints/", json=blueprint_1_create.model_dump())
    assert response_1.status_code == 201
    blueprint_1_id = response_1.json()["id"]
    assert blueprint_1_id is not None

    blueprint_2_create = BlueprintCreate.model_validate(blueprint_data_2)
    response_2 = catalog_client.post("/catalog/blueprints/", json=blueprint_2_create.model_dump())
    assert response_2.status_code == 201
    blueprint_2_id = response_2.json()["id"]
    assert blueprint_2_id is not None


def test_launch_guild_from_blueprint(setup_data, catalog_client):
    """
    Test the endpoint to launch a guild from a blueprint.
    """
    # Create a blueprint with a valid GuildSpec
    blueprint_data = {
        "name": "Echo App",
        "description": "An app that echoes the input",
        "exposure": "private",
        "author_id": setup_data["user_id"],
        "organization_id": setup_data["organization_id"],
        "version": "1.0.0",
        "spec": {
            "name": "Echo guild",
            "description": "some description",
            "properties": {},
            "agents": [
                {
                    "name": "echo_agent",
                    "description": "Echo Agent",
                    "class_name": "rustic_ai.core.agents.testutils.echo_agent.EchoAgent",
                    "additional_topics": ["echo_topic"],
                    "properties": {},
                    "listen_to_default_topic": False,
                    "act_only_when_tagged": False,
                    "dependency_map": {},
                },
            ],
            "dependency_map": {},
            "routes": {
                "steps": [
                    {
                        "agent_type": "rustic_ai.agents.utils.user_proxy_agent.UserProxyAgent",
                        "method_name": "unwrap_and_forward_message",
                        "destination": {"topic": "echo_topic"},
                        "route_times": 1,
                    },
                    {
                        "agent": {"name": "echo_agent"},
                        "destination": {"topic": "user_message_broadcast"},
                        "route_times": 1,
                    },
                ]
            },
        },
        "category_id": setup_data["category"].id,
    }

    blueprint_create = BlueprintCreate.model_validate(blueprint_data)
    response = catalog_client.post("/catalog/blueprints/", json=blueprint_create.model_dump())
    assert response.status_code == 201
    blueprint_id = response.json()["id"]

    # Test successful guild launch
    launch_request = LaunchGuildFromBlueprintRequest(
        guild_name="My New Guild",
        user_id=setup_data["user_id"],
        org_id=setup_data["organization_id"],
        description="A custom guild description",
    )

    launch_response = catalog_client.post(
        f"/catalog/blueprints/{blueprint_id}/guilds",
        json=launch_request.model_dump(),
        headers={"Content-Type": "application/json"},
    )

    assert launch_response.status_code == 201
    assert "id" in launch_response.json()
    guild_id = launch_response.json()["id"]

    # Verify the guild was created and associated with the blueprint
    blueprint_guild_response = catalog_client.get(f"/catalog/guilds/{guild_id}/blueprints/")
    assert blueprint_guild_response.status_code == 200
    assert blueprint_guild_response.json()["id"] == blueprint_id

    # Verify the user was added to the guild
    user_guilds_response = catalog_client.get(f"/catalog/users/{setup_data['user_id']}/guilds/")
    assert user_guilds_response.status_code == 200
    guild_ids = [guild["id"] for guild in user_guilds_response.json()]
    assert guild_id in guild_ids

    # Test error case: blueprint not found
    invalid_launch_request = LaunchGuildFromBlueprintRequest(
        guild_name="Invalid Guild", user_id=setup_data["user_id"], org_id=setup_data["organization_id"]
    )

    invalid_response = catalog_client.post(
        "/catalog/blueprints/non-existent-blueprint-id/guilds",
        json=invalid_launch_request.model_dump(),
        headers={"Content-Type": "application/json"},
    )

    assert invalid_response.status_code == 404
    assert "Blueprint not found" in invalid_response.json()["detail"]
