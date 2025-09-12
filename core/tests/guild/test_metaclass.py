from pydantic import BaseModel
import pytest

from rustic_ai.core.guild.agent import Agent, processor
from rustic_ai.core.guild.dsl import AgentSpec, BaseAgentProps
from rustic_ai.core.guild.metaprog.agent_annotations import AgentAnnotations
from rustic_ai.core.guild.metaprog.agent_registry import AgentDependency, AgentRegistry
from rustic_ai.core.guild.metaprog.constants import MetaclassConstants
from rustic_ai.core.utils import JsonDict


class MyProps(BaseAgentProps):
    foo: int = 42


class Ping(BaseModel):
    msg: str


# A non-Agent mixin that contributes dependencies via both hooks
class ExtDepsMixin:
    @processor(JsonDict, depends_on=["ext_attr_dep"])
    def ext_method_dep(self, ctx):
        pass


# Base agent with a handler and a dependency that will be overridden
class BaseAgent(Agent[MyProps]):  # type: ignore[type-arg]
    @processor(JsonDict, depends_on=["shared_service:base_var", "base_only:base"], handle_essential=True)
    def handle_raw(self, ctx):
        pass


# Subclass adds its own handler and overrides one dependency key
class SubAgent(BaseAgent, ExtDepsMixin):
    @processor(
        Ping, depends_on=["shared_service:sub_var", AgentDependency(dependency_key="sub_only", dependency_var="sub")]
    )
    def handle_ping(self, ctx):
        pass


@pytest.fixture(scope="module")
def agent_cls():
    # Accessing the class triggers metaclass processing, ensure class is loaded
    return SubAgent


def test_agent_props_type_annotation(agent_cls):
    # Metaclass should set AGENT_PROPS_TYPE to the MyProps generic
    ann = getattr(agent_cls, "__annotations__", {})
    assert MetaclassConstants.AGENT_PROPS_TYPE in ann
    assert ann[MetaclassConstants.AGENT_PROPS_TYPE] is MyProps


def test_message_handlers_registered(agent_cls):
    # Format handlers and raw handlers should be attached as class attributes
    fmt_handlers = getattr(agent_cls, MetaclassConstants.MESSAGE_HANDLERS)
    raw_handlers = getattr(agent_cls, MetaclassConstants.RAW_MESSAGE_HANDLERS)

    # Raw handler present
    raw = raw_handlers.get_handlers()
    assert "handle_raw" in raw

    # Format handler present keyed by fully-qualified model name
    ping_fmt = f"{Ping.__module__}.{Ping.__name__}"
    fm = fmt_handlers.get_handlers_for_format(ping_fmt)
    assert "handle_ping" in fm

    # Essential filtering should include only those marked handle_essential
    essential_raw = raw_handlers.get_essential_handlers()
    assert "handle_raw" in essential_raw

    essential_fmt = fmt_handlers.get_essential_handlers_for_format(ping_fmt)
    # handle_ping was not marked essential
    assert "handle_ping" not in essential_fmt


def test_dependency_aggregation_transitive_and_override(agent_cls):
    # Final dependencies should include contributions from:
    # - BaseAgent method deps: shared_service (overridden), base_only
    # - SubAgent method deps: shared_service (overrides), sub_only
    # - ExtDepsMixin attribute: ext_attr_dep

    ann = getattr(agent_cls, "__annotations__", {})
    deps = ann.get(AgentAnnotations.DEPENDS_ON)
    assert deps is not None and isinstance(deps, list)

    by_key = {d.dependency_key: d for d in deps}
    expected_keys = {"shared_service", "base_only", "sub_only", "ext_attr_dep"}
    assert expected_keys.issubset(set(by_key.keys()))

    # Override rule: subclass value for shared_service should win (sub_var)
    assert by_key["shared_service"].variable_name == "sub_var"


def test_registry_entry_contains_dependencies_and_handlers(agent_cls):
    qname = f"{agent_cls.__module__}.{agent_cls.__name__}"
    entry = AgentRegistry.get_agent(qname)
    assert entry is not None, "Agent not registered in AgentRegistry"

    # Handlers registered
    handler_names = set(entry.message_handlers.keys())
    assert {"handle_raw", "handle_ping"}.issubset(handler_names)

    # Dependencies registered
    dep_keys = {d.dependency_key for d in entry.agent_dependencies}
    assert {"shared_service", "base_only", "sub_only", "ext_attr_dep"}.issubset(dep_keys)


def test_agentspec_accepts_props_type_from_metaclass(agent_cls):
    # Ensure AgentSpec validates and assigns the correct properties type based on metaclass annotation
    spec = AgentSpec[MyProps](
        name="x",
        description="y",
        class_name=f"{agent_cls.__module__}.{agent_cls.__name__}",
        properties={"foo": 7},
    )

    assert isinstance(spec.properties, MyProps)
    assert spec.properties.foo == 7

    # subscribed topics should compute with agent id
    topics = spec.subscribed_topics
    assert any(t.startswith("agent_self_inbox:") for t in topics)
    assert any(t.startswith("agent_inbox:") for t in topics)
