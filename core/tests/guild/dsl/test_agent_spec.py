from pydantic import ValidationError
import pytest

from rustic_ai.core.guild import Agent
from rustic_ai.core.guild import agent as agent_ns
from rustic_ai.core.guild.dsl import (
    AgentSpec,
    BaseAgentProps,
    GuildSpec,
    OpaqueProps,
)
from rustic_ai.core.guild.metastore.models import AgentModel
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.core.utils.model_class import ModelClass

from core.tests.guild.sample_agents import (
    DemoAgentGenericWithoutTypedParams,
    DemoAgentProps,
    MessageDataType,
)
from core.tests.guild.simple_agent import SimpleAgent


class DummyAgentProps(BaseAgentProps):
    prop1: str
    prop2: int


class NestedResolvingProps(BaseAgentProps):
    # Mimics a real plugin/toolset config: an FQCN string is resolved to a class at
    # validation time (ImportError if the referenced package is not installed), the
    # same way ReActAgentConfig.toolset / ToolSpec.parameter_class resolve nested kinds.
    param_class: ModelClass


class NestedResolvingAgent(Agent[NestedResolvingProps]):
    @agent_ns.processor(MessageDataType)
    def handle_message(self, ctx: agent_ns.ProcessContext[MessageDataType]):
        pass


class TestAgentSpec:
    #  Create an AgentSpec instance with valid arguments for all attributes.
    def test_create_agent_spec_with_valid_arguments(self, client_properties):
        print(DemoAgentGenericWithoutTypedParams.get_qualified_class_name())
        agent_spec: AgentSpec[DemoAgentProps] = AgentSpec(
            name="Agent1",
            description="First agent",
            class_name=get_qualified_class_name(DemoAgentGenericWithoutTypedParams),
            properties=DemoAgentProps(prop1="value1", prop2=2),
        )

        assert agent_spec.name == "Agent1"
        assert agent_spec.description == "First agent"
        assert agent_spec.class_name == get_qualified_class_name(DemoAgentGenericWithoutTypedParams)
        assert type(agent_spec.props) is DemoAgentProps
        assert agent_spec.props.prop1 == "value1"
        assert agent_spec.props.prop2 == 2

    def test_create_agent_with_properties_as_dict(self, client_properties):
        agent_spec = AgentSpec[DemoAgentProps](
            name="Agent1",
            description="First agent",
            class_name=get_qualified_class_name(DemoAgentGenericWithoutTypedParams),
            properties={"prop1": "value1", "prop2": 2},
        )

        assert agent_spec.name == "Agent1"
        assert agent_spec.description == "First agent"
        assert agent_spec.class_name == get_qualified_class_name(DemoAgentGenericWithoutTypedParams)
        assert type(agent_spec.props) is DemoAgentProps
        assert agent_spec.props.prop1 == "value1"
        assert agent_spec.props.prop2 == 2

    #  Create an AgentSpec instance with the minimum required arguments.
    def test_create_agent_spec_with_minimum_arguments(self, client_properties):
        agent_spec: AgentSpec = AgentSpec(
            name="Agent1",
            description="First agent",
            class_name=get_qualified_class_name(SimpleAgent),
        )
        assert agent_spec.name == "Agent1"
        assert agent_spec.description == "First agent"
        assert agent_spec.properties == BaseAgentProps()

    #  Access the attributes of an AgentSpec instance.
    def test_access_agent_spec_attributes(self, client_properties):
        agent_spec = AgentSpec[DemoAgentProps](
            name="Agent1",
            description="First agent",
            class_name=get_qualified_class_name(DemoAgentGenericWithoutTypedParams),
            properties=DemoAgentProps(prop1="value1", prop2=2),
        )
        assert agent_spec.name == "Agent1"
        assert agent_spec.description == "First agent"
        assert get_qualified_class_name(agent_spec.props.__class__) == DemoAgentProps.get_qualified_class_name()
        assert agent_spec.props.prop1 == "value1"
        assert agent_spec.props.prop2 == 2

    #  Create an AgentSpec instance with an empty name.
    def test_create_agent_spec_with_empty_name(self, client_properties):
        with pytest.raises(ValidationError):
            AgentSpec(
                name="",
                description="First agent",
                class_name=get_qualified_class_name(SimpleAgent),
            )

    #  Create an AgentSpec instance with an empty description.
    def test_create_agent_spec_with_empty_description(self, client_properties):
        with pytest.raises(ValidationError):
            AgentSpec(
                name="Agent1",
                description="",
                class_name=get_qualified_class_name(SimpleAgent),
            )

    def test_create_agent_spec_with_invalid_class_name(self, client_properties):
        with pytest.raises(ValidationError):
            AgentSpec(
                name="Agent1",
                description="First agent",
                class_name="invalid_class_name",
            )

    def test_create_agent_spec_with_invalid_properties(self, client_properties):
        with pytest.raises(ValidationError):
            AgentSpec(
                name="Agent1",
                description="First agent",
                class_name=get_qualified_class_name(SimpleAgent),
                properties={"prop1": "value1", "prop2": 2},
            )

    def test_create_agent_spec_with_invalid_properties_type(self, client_properties):
        with pytest.raises(ValidationError):
            AgentSpec(
                name="Agent1",
                description="First agent",
                class_name=get_qualified_class_name(SimpleAgent),
                properties=DummyAgentProps(prop1="value1", prop2=2),
            )

    def test_create_agent_spec_with_unmatched_properties_type(self, client_properties):
        with pytest.raises(ValidationError):
            AgentSpec(
                name="Agent1",
                description="First agent",
                class_name=get_qualified_class_name(DemoAgentGenericWithoutTypedParams),
                properties=DummyAgentProps(prop1="value1", prop2=2),
            )

    def test_create_agent_spec_without_classname(self, client_properties):
        with pytest.raises(ValidationError):
            AgentSpec(
                name="Agent1",
                description="First agent",
            )  # type: ignore

    def test_create_agent_spec_with_non_agent_class(self, client_properties):
        with pytest.raises(ValidationError):
            AgentSpec(
                name="Agent1",
                description="First agent",
                class_name=get_qualified_class_name(DummyAgentProps),
            )


# Properties of a foreign agent whose implementation package is not installed here.
FOREIGN_PROPS = {
    "model": "gpt-4o",
    "temperature": 0.7,
    "toolset": {"kind": "not_installed.pkg.Toolset", "nested": {"a": [1, 2, 3]}},
}


def _foreign_agent_data() -> dict:
    return {
        "id": "foreign1",
        "name": "Foreign Agent",
        "description": "An agent whose class is not importable in this environment",
        "class_name": "not_installed.pkg.SomeAgent",
        "properties": dict(FOREIGN_PROPS),
    }


class TestAgentSpecOpaqueProps:
    """
    Isolated per-agent deployments: an environment lacking an agent's package must
    still deserialize/hold/re-persist that agent's spec, with its properties kept as
    a lossless OpaqueProps rather than raising. Fail-fast stays available on demand
    via the ``require_agent_class`` validation context.
    """

    def test_missing_class_degrades_to_opaque_and_roundtrips(self):
        spec = AgentSpec.model_validate(_foreign_agent_data())

        assert isinstance(spec.properties, OpaqueProps)
        # Lossless round-trip, both directly on the props and through the AgentSpec
        # field (the latter is exercised when a full guild_spec is re-dumped, e.g.
        # GuildManagerAgent bootstrap / refresh).
        assert spec.properties.model_dump() == FOREIGN_PROPS
        assert spec.model_dump()["properties"] == FOREIGN_PROPS
        # The metastore re-persist path (AgentModel.from_agent_spec -> properties
        # model_dump) must not narrow or corrupt a peer's stored config.
        assert AgentModel.from_agent_spec("g1", spec).properties == FOREIGN_PROPS

    def test_strict_context_rejects_missing_class(self):
        with pytest.raises(ValidationError):
            AgentSpec.model_validate(_foreign_agent_data(), context={"require_agent_class": True})

    def test_full_guild_with_one_missing_agent_loads(self):
        guild = GuildSpec.model_validate(
            {
                "name": "MixedGuild",
                "description": "One core agent, one uninstalled agent",
                "agents": [
                    {
                        "id": "core1",
                        "name": "Core Agent",
                        "description": "A core agent present in this environment",
                        "class_name": get_qualified_class_name(SimpleAgent),
                    },
                    _foreign_agent_data(),
                ],
            }
        )

        by_id = {a.id: a for a in guild.agents}
        assert isinstance(by_id["foreign1"].properties, OpaqueProps)
        assert not isinstance(by_id["core1"].properties, OpaqueProps)

        # The same guild fails fast under strict validation (env expected to have
        # every agent class, e.g. CI/authoring).
        with pytest.raises(ValidationError):
            GuildSpec.model_validate(guild.model_dump(), context={"require_agent_class": True})

    def test_present_class_types_normally(self):
        spec = AgentSpec[DemoAgentProps](
            name="Agent1",
            description="First agent",
            class_name=get_qualified_class_name(DemoAgentGenericWithoutTypedParams),
            properties={"prop1": "value1", "prop2": 2},
        )

        assert not isinstance(spec.properties, OpaqueProps)
        assert type(spec.props) is DemoAgentProps
        assert spec.props.prop1 == "value1"


class TestAgentSpecNestedPlugins:
    """
    The agent class itself is importable, but a nested plugin/toolset class referenced
    by its props (like a ReActAgent whose toolset lives in a package this environment
    lacks) is not. Deserialization must still degrade the whole props to OpaqueProps by
    default, so a container can hold a peer it does not run.
    """

    def _data(self, param_class: str) -> dict:
        return {
            "id": "nested1",
            "name": "Nested Agent",
            "description": "Agent whose props reference a nested class",
            "class_name": get_qualified_class_name(NestedResolvingAgent),
            "properties": {"param_class": param_class},
        }

    def test_nested_missing_plugin_degrades_to_opaque(self):
        spec = AgentSpec.model_validate(self._data("not_installed.pkg.SomeModel"))

        assert isinstance(spec.properties, OpaqueProps)
        # The unresolved FQCN string is preserved verbatim (never imported).
        assert spec.properties.model_dump() == {"param_class": "not_installed.pkg.SomeModel"}
        assert spec.model_dump()["properties"] == {"param_class": "not_installed.pkg.SomeModel"}

    def test_nested_missing_plugin_strict_raises(self):
        with pytest.raises(ValidationError):
            AgentSpec.model_validate(
                self._data("not_installed.pkg.SomeModel"),
                context={"require_agent_class": True},
            )

    def test_nested_present_plugin_types_normally(self):
        spec = AgentSpec.model_validate(self._data(get_qualified_class_name(MessageDataType)))

        assert not isinstance(spec.properties, OpaqueProps)
        assert spec.props.param_class is MessageDataType

    def test_guild_manager_props_hold_peers_opaque_even_under_strict(self):
        # A core-only GuildManagerAgent embeds a full guild_spec of peers. Strict
        # validation of the GMA must NOT require those peers' plugin classes — they
        # are held opaquely; strictness does not recurse into the embedded guild_spec.
        foreign = {
            "id": "peer1",
            "name": "Peer",
            "description": "A peer plugin agent not installed here",
            "class_name": "not_installed.pkg.SomeAgent",
            "properties": {"x": 1},
        }
        gma = {
            "name": "Guild Manager",
            "description": "Manages the guild",
            "class_name": "rustic_ai.core.agents.system.guild_manager_agent.GuildManagerAgent",
            "properties": {
                "guild_spec": {"name": "G", "description": "d", "agents": [foreign]},
                "database_url": "sqlite://",
                "organization_id": "org1",
            },
        }

        spec = AgentSpec.model_validate(gma, context={"require_agent_class": True})
        peer = spec.props.guild_spec.agents[0]
        assert isinstance(peer.properties, OpaqueProps)
