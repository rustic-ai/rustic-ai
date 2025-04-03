from rustic_ai.core.agents.testutils.probe_agent import ProbeAgent
from rustic_ai.core.guild.agent import Agent
from rustic_ai.core.guild.builders import AgentBuilder
from rustic_ai.core.guild.guild import Guild

from .sample_agents import (
    DemoAgentGenericWithoutTypedSpec,
    DemoAgentProps,
)
from .simple_agent import SimpleAgent


class TestAgent:
    def test_create_agent_with_valid_arguments(self):
        agent_id = "p1"
        name = "John"
        description = "A bot agent"

        agent: Agent = AgentBuilder(SimpleAgent).set_id(agent_id).set_name(name).set_description(description).build()

        assert agent.id == agent_id
        assert agent.name == name
        assert agent.description == description

    def test_agent_client_message_handling(self, guild: Guild, probe_agent: ProbeAgent):
        agent_id = "p2"
        name = "Bot"
        description = "A bot agent"

        agent: SimpleAgent = (
            AgentBuilder(SimpleAgent).set_id(agent_id).set_name(name).set_description(description).build()
        )

        guild._add_local_agent(agent)
        guild._add_local_agent(probe_agent)

        probe_agent.publish_dict(guild.DEFAULT_TOPIC, {"key1": "value1"})

        assert len(agent.received_messages) == 1
        assert agent.received_messages[0].payload["key1"] == "value1"

    def test_agent_instantion_with_parameters(self):
        demo_props = DemoAgentProps(prop1="value1", prop2=2)

        agent: Agent = (
            AgentBuilder(DemoAgentGenericWithoutTypedSpec)
            .set_name("simple")
            .set_description("simple agent")
            .set_properties(demo_props)
            .build()
        )

        assert agent._agent_spec.props.prop1 == "value1"

    def test_agent_instantion_with_parameters_as_dict(self):
        agent: Agent = (
            AgentBuilder(DemoAgentGenericWithoutTypedSpec)
            .set_name("simple")
            .set_description("simple agent")
            .set_properties({"prop1": "value1", "prop2": 2})
            .build()
        )

        assert agent._agent_spec.props.prop1 == "value1"
        assert agent._agent_spec.props.prop2 == 2
