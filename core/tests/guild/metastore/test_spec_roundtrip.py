from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import Column, MetaData, Table, create_engine
from sqlmodel import Session, SQLModel

from rustic_ai.core.guild.agent_ext.depends.dependency_resolver import DependencySpec
from rustic_ai.core.guild.dsl import (
    AgentSpec,
    CelPredicate,
    GatewayConfig,
    GuildSpec,
    JSONataPredicate,
    QOSSpec,
    ResourceSpec,
    TypeEqualsPredicate,
)
from rustic_ai.core.guild.metastore.guild_store import GuildStore
from rustic_ai.core.guild.metastore.models import (
    AgentModel,
    AgentStatus,
    GuildModel,
    GuildRoutes,
    RouteStatus,
)
from rustic_ai.core.messaging.core.message import (
    AgentTag,
    FunctionalTransformer,
    PayloadTransformer,
    RoutingDestination,
    RoutingOrigin,
    RoutingRule,
    RoutingSlip,
    StateTransformer,
)


def complete_spec():
    timestamp = datetime(2026, 11, 27, tzinfo=timezone.utc)
    dependency = {
        "class_name": "example.Resolver",
        "properties": {"options": {"enabled": False, "limit": 0, "timestamp": timestamp.isoformat()}},
    }
    agent = {
        "id": "z-agent",
        "name": "Foreign Agent",
        "description": "Keep the definition without importing its implementation",
        "class_name": "example.not_installed.ForeignAgent",
        "additional_topics": ["requests", "references"],
        "properties": {"nested": {"items": [1, False, None], "timestamp": timestamp}, "empty": {}, "zero": 0},
        "listen_to_default_topic": False,
        "act_only_when_tagged": True,
        "predicates": {
            "first": {"predicate_type": "jsonata_fn", "expression": "true"},
            "second": {"predicate_type": "cel_fn", "expression": "true"},
            "third": {"predicate_type": "type_equals", "expected_type": "request"},
        },
        "dependency_map": {"local": deepcopy(dependency)},
        "additional_dependencies": ["shared", "local"],
        "resources": {"num_cpus": 0.5, "num_gpus": 0, "custom_resources": {"accelerator": 2}},
        "qos": {"timeout": 30, "retry_count": 0, "latency": 20},
    }
    route = {
        "agent": {"id": "z-agent", "name": "Foreign Agent"},
        "agent_type": "example.not_installed.ForeignAgent",
        "method_name": "first",
        "origin_filter": {
            "origin_sender": {"id": "user", "name": "User"},
            "origin_topic": "requests",
            "origin_message_format": "example.Input",
        },
        "message_format": "example.Output",
        "destination": {
            "topics": ["only-one-topic"],
            "recipient_list": [{"id": "a-agent", "name": None}],
            "priority": 0,
        },
        "mark_forwarded": True,
        "route_times": -1,
        "transformer": {
            "style": "simple",
            "output_format": "example.Transformed",
            "expression_type": "cel",
            "expression": "payload",
        },
        "agent_state_update": {"expression_type": "cel", "update_format": "json-patch", "state_update": "[]"},
        "guild_state_update": {
            "expression_type": "jsonata",
            "update_format": "json-merge-patch",
            "state_update": "{'count': 1}",
        },
        "process_status": "error",
        "reason": "Keep route metadata",
    }
    second_agent = deepcopy(agent) | {
        "id": "a-agent",
        "name": "Second Agent",
        "listen_to_default_topic": True,
        "act_only_when_tagged": False,
    }
    functional_route = deepcopy(route) | {
        "method_name": "second",
        "transformer": {
            "style": "content_based_router",
            "expression_type": "jsonata",
            "handler": "{'payload': payload}",
        },
        "destination": {"topics": [], "recipient_list": [], "priority": None},
        "origin_filter": {},
        "route_times": 0,
        "mark_forwarded": False,
        "process_status": "completed",
    }
    data = {
        "id": "complete-guild",
        "name": "Complete Guild",
        "description": "Exercise every GuildSpec field through storage",
        "properties": {
            "execution_engine": "rustic_ai.core.guild.execution.sync.sync_exec_engine.SyncExecutionEngine",
            "messaging": {
                "backend_module": "rustic_ai.core.messaging.backend",
                "backend_class": "InMemoryMessagingBackend",
                "backend_config": {"custom": [False, 0], "timestamp": timestamp},
            },
            "client_type": "example.Client",
            "client_properties": {"window": 0},
            "state_manager": "example.StateManager",
            "state_manager_config": {"persist": True},
            "conversation_history_size": 12,
            "custom": {"list": [None, False, 0, ""], "empty": {}},
        },
        "agents": [agent, second_agent],
        "dependency_map": {"shared": dependency},
        "routes": {"steps": [route, functional_route, deepcopy(route)]},
        "gateway": {
            "enabled": False,
            "input_formats": ["example.Input"],
            "output_formats": ["example.Output"],
            "returned_formats": ["example.Result"],
        },
    }
    # Adding a model field must expand this fixture, even when its default would mask a loss.
    for model, values in [
        (GuildSpec, data),
        (AgentSpec, agent),
        (ResourceSpec, agent["resources"]),
        (QOSSpec, agent["qos"]),
        (RoutingRule, route),
        (RoutingOrigin, route["origin_filter"]),
        (RoutingDestination, route["destination"]),
        (GatewayConfig, data["gateway"]),
        (DependencySpec, dependency),
        (AgentTag, route["agent"]),
        (RoutingSlip, data["routes"]),
        (PayloadTransformer, route["transformer"]),
        (FunctionalTransformer, functional_route["transformer"]),
        (StateTransformer, route["agent_state_update"]),
        (JSONataPredicate, agent["predicates"]["first"]),
        (CelPredicate, agent["predicates"]["second"]),
        (TypeEqualsPredicate, agent["predicates"]["third"]),
    ]:
        assert set(values) == set(model.model_fields), f"Update complete_spec for {model.__name__}"
    return GuildSpec.model_validate(data)


@pytest.mark.parametrize("use_defaults", [False, True])
@pytest.mark.parametrize("gateway_enabled", [False, True, None])
def test_complete_guild_spec_survives_database_reopen(tmp_path, use_defaults, gateway_enabled):
    spec = complete_spec()
    if use_defaults:
        spec = GuildSpec.model_validate({"id": "default-guild", "name": "Defaults", "description": "Keep defaults"})
    elif gateway_enabled is None:
        spec.gateway = None
    else:
        spec.gateway.enabled = gateway_enabled
    expected = spec.model_dump(mode="json")
    engine = create_engine("sqlite:///" + str(tmp_path / "spec.db"))
    SQLModel.metadata.create_all(engine)
    try:
        store = GuildStore(engine)
        store.add_guild(spec, "test-org")
        for agent in spec.agents:
            store.add_agent(spec.id, agent)
        assert spec.model_dump(mode="json") == expected, "Saving must not mutate the input"
    finally:
        engine.dispose()
    engine = create_engine("sqlite:///" + str(tmp_path / "spec.db"))
    try:
        loaded = GuildStore(engine).get_guild(spec.id)
        assert loaded is not None
        assert loaded.to_guild_spec().model_dump(mode="json") == expected
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "destination", [None, {}, {"topics": ""}, {"topics": []}, {"topics": ["one"]}, {"priority": 0}]
)
@pytest.mark.parametrize("origin_filter", [None, {}, {"origin_sender": {"id": None, "name": ""}}])
def test_route_shapes_survive_storage(tmp_path, destination, origin_filter):
    rule = RoutingRule.model_validate(
        {
            "agent_type": "example.Agent",
            "agent": {"id": None, "name": ""},
            "destination": destination,
            "origin_filter": origin_filter,
        }
    )
    engine = create_engine("sqlite:///" + str(tmp_path / "route.db"))
    SQLModel.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            row = GuildRoutes.from_routing_rule("guild", rule)
            session.add(row)
            session.commit()
            identifier = row.id
        with Session(engine) as session:
            loaded = session.get(GuildRoutes, (identifier, "guild"))
            assert loaded.to_routing_rule().model_dump(mode="json") == rule.model_dump(mode="json")
    finally:
        engine.dispose()


def test_dynamic_definitions_and_lifecycle_updates_survive_reopen(tmp_path):
    spec = complete_spec()
    expected = spec.model_dump(mode="json")
    appended_agent = spec.agents[0].model_copy(update={"id": "0-last-agent", "name": "Appended"})
    appended_route = spec.routes.steps[0].model_copy(update={"method_name": "appended"})
    expected["agents"] = [expected["agents"][1], appended_agent.model_dump(mode="json")]
    expected["agents"][0]["name"] = "Renamed"
    expected["agents"][0]["properties"]["new"] = False
    expected["routes"]["steps"] = [expected["routes"]["steps"][0], expected["routes"]["steps"][2]]
    expected["routes"]["steps"][0].update(route_times=0, mark_forwarded=False, process_status="completed", reason=None)
    expected["routes"]["steps"].append(appended_route.model_dump(mode="json"))
    url = "sqlite:///" + str(tmp_path / "dynamic.db")
    engine = create_engine(url)
    SQLModel.metadata.create_all(engine)
    try:
        store = GuildStore(engine)
        store.add_guild(spec, "test-org")
        for agent in spec.agents:
            store.add_agent(spec.id, agent)
        with Session(engine) as session:
            guild = GuildModel.get_by_id(session, spec.id)
            guild.agents[0].status = AgentStatus.DELETED
            guild.agents[1].name = "Renamed"
            guild.agents[1].properties["new"] = False
            guild.routes[1].status = RouteStatus.DELETED
            guild.routes[0].route_times = 0
            guild.routes[0].mark_forwarded = False
            guild.routes[0].process_status = "completed"
            guild.routes[0].reason = None
            session.add(guild)
            session.commit()
        store.add_agent(spec.id, appended_agent)
        with Session(engine) as session:
            session.add(
                GuildRoutes.from_routing_rule(
                    spec.id, appended_route, position=GuildRoutes.next_position(session, spec.id)
                )
            )
            session.commit()
    finally:
        engine.dispose()
    engine = create_engine(url)
    try:
        loaded = GuildStore(engine).get_guild(spec.id)
        assert loaded.to_guild_spec().model_dump(mode="json") == expected
    finally:
        engine.dispose()


def test_definition_migration_keeps_legacy_guild_readable(tmp_path):
    spec = complete_spec()
    guild = GuildModel.from_guild_spec(spec, "test-org")
    guild.spec_data = None
    guild.agents = [AgentModel.from_agent_spec(spec.id, agent) for agent in spec.agents]
    for agent in guild.agents:
        agent.spec_data = None
    for route in guild.routes:
        route.spec_data = None
    # Legacy storage has already discarded some values. Migration must preserve
    # the remaining definition, not guess at the unavailable original values.
    # Legacy rows have no ordinal; ties use IDs until the original spec is re-saved.
    guild.agents = sorted(guild.agents, key=lambda agent: agent.id)
    guild.routes = sorted(guild.routes, key=lambda route: route.id)
    expected = guild.to_guild_spec().model_dump(mode="json")
    legacy = MetaData()
    for model in [GuildModel, AgentModel, GuildRoutes]:
        Table(
            model.__tablename__,
            legacy,
            *[
                Column(c.name, c.type, primary_key=c.primary_key, nullable=c.nullable)
                for c in model.__table__.columns
                if c.name not in {"spec_data", "position"}
            ],
        )
    engine = create_engine("sqlite:///" + str(tmp_path / "legacy-spec.db"))
    legacy.create_all(engine)
    try:
        with engine.begin() as connection:
            connection.execute(legacy.tables["guilds"].insert(), guild.model_dump(exclude={"spec_data"}))
            for agent in guild.agents:
                connection.execute(
                    legacy.tables["agents"].insert(), agent.model_dump(exclude={"spec_data", "position"})
                )
            for route in guild.routes:
                connection.execute(
                    legacy.tables["guild_routes"].insert(), route.model_dump(exclude={"spec_data", "position"})
                )
            migration = Path(__file__).resolve().parents[4] / "scripts/migrations/preserve_guild_spec_definitions.sql"
            for statement in migration.read_text().split(";"):
                if statement.strip():
                    connection.exec_driver_sql(statement)
        engine.dispose()
        loaded = GuildStore(engine).get_guild(spec.id)
        assert loaded.to_guild_spec().model_dump(mode="json") == expected
    finally:
        engine.dispose()
