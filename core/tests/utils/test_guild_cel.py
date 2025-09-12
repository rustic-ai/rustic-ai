import asyncio
import os
from typing import Any, Dict, List, Optional

from pydantic import BaseModel
import pytest
import shortuuid

from rustic_ai.core import Guild, GuildTopics, Priority
from rustic_ai.core.agents.system.models import (
    UserAgentCreationRequest,
    UserAgentCreationResponse,
)
from rustic_ai.core.agents.testutils import ProbeAgent
from rustic_ai.core.agents.testutils.echo_agent import EchoAgent
from rustic_ai.core.agents.utils import UserProxyAgent
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder, RouteBuilder
from rustic_ai.core.guild.metastore import Metastore
from rustic_ai.core.messaging.core.message import (
    AgentTag,
    ExpressionType,
    Message,
    RoutingSlip,
)
from rustic_ai.core.utils import GemstoneGenerator
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name


class PurchaseOrderRequest(BaseModel):
    order_id: str
    items: List[Dict[str, Any]]
    customer: str


class ItemProcessingResult(BaseModel):
    id: Optional[str]
    quantity: Optional[int]


class TestSplitterGuild:

    @pytest.fixture
    def routing_slip(self) -> RoutingSlip:
        route = (
            RouteBuilder(AgentTag(name="Echo Agent 1"))
            .on_message_format(PurchaseOrderRequest)
            .set_destination_topics("echo_2")
            .set_route_times(-1)
            .set_payload_transformer(
                expression_type=ExpressionType.CEL, payload_xform="items[0]", output_type=ItemProcessingResult
            )
            .build()
        )

        slip = RoutingSlip(steps=[route])
        return slip

    @pytest.fixture
    def rgdatabase(self):
        db = "sqlite:///cel_fn_demo.db"

        if os.path.exists("cel_fn_demo.db"):
            os.remove("cel_fn_demo.db")

        Metastore.initialize_engine(db)
        Metastore.get_engine(db)
        Metastore.create_db()
        yield db
        Metastore.drop_db()

    @pytest.fixture
    def guild(self, routing_slip, rgdatabase):
        guild_builder = GuildBuilder(
            guild_id=f"cel_fn_demo{shortuuid.uuid()}",
            guild_name="CelFnGuild",
            guild_description="Demonstrates cel fn",
        )

        echo_agent_1 = (
            AgentBuilder(EchoAgent)
            .set_id("echo_agent_1")
            .set_name("Echo Agent 1")
            .set_description("Echoes message")
            .add_additional_topic("echo_1")
            .listen_to_default_topic(False)
            .build_spec()
        )

        echo_agent_2 = (
            AgentBuilder(EchoAgent)
            .set_id("echo_agent_2")
            .set_name("Echo Agent 2")
            .set_description("Echoes message")
            .add_additional_topic("echo_2")
            .listen_to_default_topic(False)
            .build_spec()
        )

        guild_builder.add_agent_spec(echo_agent_1).add_agent_spec(echo_agent_2)

        guild = guild_builder.set_routes(routing_slip).bootstrap(rgdatabase, "dummy_ord")

        yield guild
        guild.shutdown()

    @pytest.mark.asyncio
    async def test_cel_fun(self, guild: Guild, generator: GemstoneGenerator):

        probe_sepc = (
            AgentBuilder(ProbeAgent)
            .set_id("test_agent")
            .set_name("Test Agent")
            .set_description("A test agent")
            .add_additional_topic(UserProxyAgent.BROADCAST_TOPIC)
            .add_additional_topic(GuildTopics.SYSTEM_TOPIC)
            .add_additional_topic("echo_2")
            .build_spec()
        )

        probe_agent: ProbeAgent = guild._add_local_agent(probe_sepc)

        probe_agent.publish_dict(
            topic=GuildTopics.SYSTEM_TOPIC,
            payload=UserAgentCreationRequest(user_id="test_user", user_name="test_user").model_dump(),
            format=UserAgentCreationRequest,
        )

        await asyncio.sleep(2)

        system_messages = probe_agent.get_messages()
        assert len(system_messages) == 1

        user_created = system_messages[0]
        assert user_created.format == get_qualified_class_name(UserAgentCreationResponse)
        assert user_created.payload["user_id"] == "test_user"
        assert user_created.payload["status_code"] == 201

        probe_agent.clear_messages()

        test_order = PurchaseOrderRequest(
            order_id="PO-12345",
            customer="ACME Corp",
            items=[{"id": "item-001", "quantity": 2}, {"id": "item-002", "quantity": 1}],
        )

        payload = test_order.model_dump()
        message_format = get_qualified_class_name(PurchaseOrderRequest)

        id_obj = generator.get_id(Priority.NORMAL)
        wrapped_message = Message(
            id_obj=id_obj,
            topics="echo_1",
            payload=payload,
            format=message_format,
            sender=AgentTag(id="test_agent", name="TestAgent"),
        )
        probe_agent.publish(
            topic=UserProxyAgent.get_user_inbox_topic("test_user"),
            payload=wrapped_message,
        )

        await asyncio.sleep(8)

        messages = probe_agent.get_messages()
        messages = [msg for msg in messages if msg.topics == "echo_2"]
        assert len(messages) > 0
        assert messages[-1].payload["id"] == "item-001"
        assert messages[-1].payload["quantity"] == 2
