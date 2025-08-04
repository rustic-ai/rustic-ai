import time

from rustic_ai.core.agents.testutils.probe_agent import ProbeAgent
from rustic_ai.core.guild.builders import AgentBuilder
from rustic_ai.core.guild.dsl import AgentSpec
from rustic_ai.core.guild.guild import Guild

from .simple_agent import SimpleAgent


class TestAgent:

    def test_agent_client_message_handling(self, guild: Guild, probe_spec):
        agent_id = "p2"
        name = "Bot"
        description = "A bot agent"

        agent_spec: AgentSpec = (
            AgentBuilder(SimpleAgent).set_id(agent_id).set_name(name).set_description(description).build_spec()
        )

        agent = guild._add_local_agent(agent_spec)
        probe_agent: ProbeAgent = guild._add_local_agent(probe_spec)  # type: ignore

        probe_agent.publish_dict(guild.DEFAULT_TOPIC, {"key1": "value1"})

        # Allow time for asynchronous message delivery
        time.sleep(0.5)

        assert len(agent.received_messages) == 1
        assert agent.received_messages[0].payload["key1"] == "value1"
