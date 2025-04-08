import pytest
from pydantic import ValidationError

from rustic_ai.core.guild.dsl import AgentSpec, BaseAgentProps
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name

from core.tests.guild.sample_agents import (
    DemoAgentGenericWithoutTypedParams,
    DemoAgentProps,
)
from core.tests.guild.simple_agent import SimpleAgent


class DummyAgentProps(BaseAgentProps):
    prop1: str
    prop2: int


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
