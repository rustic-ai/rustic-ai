from rustic_ai.core.agents.testutils.echo_agent import EchoAgent
from rustic_ai.core.agents.testutils.probe_agent import ProbeAgent
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.guild.dsl import AgentSpec
from rustic_ai.core.messaging.core.message import AgentTag


class TestAgentTagging:

    def test_only_when_tagged(self):

        # 2 Agents that only act when tagged
        echo1: AgentSpec = (
            AgentBuilder(EchoAgent)
            .set_id("echo1")
            .set_name("Echo1")
            .set_description("Responds when tagged")
            .act_only_when_tagged(True)
            .build_spec()
        )
        echo2: AgentSpec = (
            AgentBuilder(EchoAgent)
            .set_id("echo2")
            .set_name("Echo2")
            .set_description("Responds when tagged")
            .act_only_when_tagged(True)
            .build_spec()
        )

        # 1 Agent that acts regardless of tagging
        echo3: AgentSpec = (
            AgentBuilder(EchoAgent)
            .set_id("echo3")
            .set_name("Echo3")
            .set_description("Always echoes")
            .act_only_when_tagged(False)
            .build_spec()
        )

        guild = (
            GuildBuilder()
            .set_name("Tagging Guild")
            .set_description("Guild to test agent tagging")
            .add_agent_spec(echo1)
            .add_agent_spec(echo2)
            .add_agent_spec(echo3)
            .launch()
        )

        probe_agent = AgentBuilder(ProbeAgent).set_name("probe").set_description("Probe agent").build()

        guild._add_local_agent(probe_agent)

        probe_agent.publish_dict(
            guild.DEFAULT_TOPIC,
            {"key1": "value1"},
            recipient_list=[AgentTag(id="echo1")],
        )

        msgs1 = probe_agent.get_messages()

        assert len(msgs1) == 3

        senders = {msg.sender.id for msg in msgs1}

        assert len(senders) == 2

        assert "echo1" in senders
        assert "echo3" in senders

        probe_agent.clear_messages()

        probe_agent.publish_dict(
            guild.DEFAULT_TOPIC,
            {"key1": "value1"},
            recipient_list=[AgentTag(id="echo2")],
        )

        msgs2 = probe_agent.get_messages()

        assert len(msgs2) == 3

        senders = {msg.sender.id for msg in msgs2}

        assert len(senders) == 2

        assert "echo2" in senders
        assert "echo3" in senders
        assert "echo1" not in senders

        guild.shutdown()
