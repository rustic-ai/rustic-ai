from pydantic import BaseModel

from rustic_ai.core.agents.eip.basic_wiring_agent import BasicWiringAgent
from rustic_ai.core.agents.testutils import EchoAgent
from rustic_ai.core.agents.utils import UserProxyAgent
from rustic_ai.core.guild.builders import AgentBuilder, RouteBuilder
from rustic_ai.core.guild.dsl import AgentSpec
from rustic_ai.core.messaging.core.message import (
    AgentTag,
    FunctionalTransformer,
    PayloadTransformer,
    ProcessStatus,
    StateTransformer,
)
from rustic_ai.core.utils.jexpr import JObj, JxScript


class DummyModel(BaseModel):
    key1: str


class TestRouteBuilder:

    def test_route_builder_with_payload_transformer(self):
        agent_tag = AgentTag(name="agent1")
        recipient_2 = AgentTag(name="recipient2")

        payload_script = JxScript(JObj({"key1": "value1"}))
        agent_state_script = JxScript(JObj({"agent_key_1": "value_1"}))
        guild_state_script = JxScript(JObj({"guild_key_1": "value_1"}))

        # Build the route
        route = (
            RouteBuilder(agent_tag)
            .from_method("handle_input")
            .on_message_format("TextMessage")
            .filter_on_origin(
                origin_sender=recipient_2,
                origin_topic="origin.topic",
                origin_message_format="OriginFormat",
            )
            .set_destination_topics(["topic1", "topic2"])
            .add_recipients([recipient_2])
            .mark_forwarded(True)
            .set_route_times(3)
            .set_payload_transformer(output_type=DummyModel, payload_xform=payload_script)
            .set_agent_state_update(update_agent_state=agent_state_script)
            .set_guild_state_update(update_guild_state=guild_state_script)
            .set_process_status(ProcessStatus.RUNNING)
            .build()
        )

        assert route.agent == AgentTag(name=agent_tag.name)
        assert route.method_name == "handle_input"
        assert route.message_format == "TextMessage"
        assert route.origin_filter.origin_topic == "origin.topic"
        assert route.origin_filter.origin_sender.name == recipient_2.name
        assert route.origin_filter.origin_message_format == "OriginFormat"
        assert route.destination.topics == ["topic1", "topic2"]
        assert len(route.destination.recipient_list) == 1
        assert route.mark_forwarded is True
        assert route.route_times == 3
        assert isinstance(route.transformer, PayloadTransformer)
        assert isinstance(route.agent_state_update, StateTransformer)
        assert isinstance(route.guild_state_update, StateTransformer)
        assert route.process_status == ProcessStatus.RUNNING

    def test_route_builder_with_functional_transformer(self):
        test_agent_spec: AgentSpec = (
            AgentBuilder(BasicWiringAgent)
            .set_id("test_agent")
            .set_name("Test Agent")
            .set_description("TestAgent")
            .add_additional_topic("TEST")
            .listen_to_default_topic(False)
            .build_spec()
        )

        functional_script = JxScript(JObj({"payload": JObj({"key1": "value1"}), "format": "testing"}))

        # Build the route
        route = (
            RouteBuilder(from_agent=test_agent_spec)
            .from_method("handle_func_input")
            .on_message_format("JsonMessage")
            .set_functional_transformer(functional_xform=functional_script)
            .build()
        )

        assert route.agent.name == test_agent_spec.name
        assert route.method_name == "handle_func_input"
        assert route.message_format == "JsonMessage"
        assert isinstance(route.transformer, FunctionalTransformer)
        assert '{"payload": {"key1": "value1"}, "format": "testing"}' in route.transformer.handler

    def test_route_builder_with_reason(self):
        # Build the route
        route = (
            RouteBuilder(EchoAgent)
            .set_destination_topics(UserProxyAgent.get_user_outbox_topic("test_user"))
            .set_reason("simply doing my job")
            .set_process_status(ProcessStatus.COMPLETED)
            .build()
        )

        assert route.reason == "simply doing my job"
        assert route.process_status == ProcessStatus.COMPLETED
