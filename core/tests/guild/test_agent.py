import time

from rustic_ai.core.agents.testutils.probe_agent import ProbeAgent
from rustic_ai.core.guild.builders import AgentBuilder
from rustic_ai.core.guild.dsl import AgentSpec, GuildTopics
from rustic_ai.core.guild.guild import Guild

from core.tests.guild.simple_agent import SimpleAgent, SimpleErrorAgent


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

    def test_agent_error_handling(self, guild: Guild):
        agent_id = "p2"
        name = "Bot"
        description = "A bot agent"

        agent_spec: AgentSpec = (
            AgentBuilder(SimpleErrorAgent).set_id(agent_id).set_name(name).set_description(description).build_spec()
        )

        probe_spec: AgentSpec = (
            AgentBuilder(ProbeAgent)
            .set_id("probe")
            .set_name("Probe")
            .set_description("Probe agent")
            .add_additional_topic(GuildTopics.ERROR_TOPIC)
            .build_spec()
        )

        guild._add_local_agent(agent_spec)
        probe_agent: ProbeAgent = guild._add_local_agent(probe_spec)  # type: ignore

        probe_agent.publish_dict(guild.DEFAULT_TOPIC, {"key1": "value1"})

        # Allow time for asynchronous message delivery
        time.sleep(0.5)

        messages = probe_agent.get_messages()
        assert len(messages) == 1
        assert messages[0].payload["error_message"] == "An error occurred"
        assert messages[0].topic_published_to == GuildTopics.ERROR_TOPIC

    # def test_agent_with_multiple_handlers(self, guild: Guild):
    #     agent_id = "p2"
    #     name = "Bot"
    #     description = "A bot agent"
    #
    #     agent_spec: AgentSpec = (
    #         AgentBuilder(MultiProcessAgent).set_id(agent_id).set_name(name).set_description(description).build_spec()
    #     )
    #
    #     guild._add_local_agent(agent_spec)
    #
    #     probe_agent: ProbeAgent = guild._add_local_agent(
    #         AgentBuilder(ProbeAgent).set_id("probe").set_name("Probe").set_description("Probe agent").build_spec()
    #     )
    #
    #     probe_agent.publish(guild.DEFAULT_TOPIC, DummyMessage(key1="value1", key2=5))
    #
    #     time.sleep(0.5)
    #
    #     messages = probe_agent.get_messages()
    #     assert len(messages) == 1
    #     assert messages[0].format == get_qualified_class_name(DummyResponseOne)
    #     assert messages[0].payload["key1"] == "value1"
    #     assert messages[0].payload["key2"] == 5
    #
    #     probe_agent.clear_messages()
    #
    #     probe_agent.publish(guild.DEFAULT_TOPIC, DummyMessage(key1="value2", key2=11))
    #
    #     time.sleep(0.5)
    #
    #     messages = probe_agent.get_messages()
    #     assert len(messages) == 2
    #
    #     formats = [msg.format for msg in messages]
    #
    #     assert get_qualified_class_name(DummyResponseOne) in formats
    #     assert get_qualified_class_name(DummyResponseTwo) in formats
