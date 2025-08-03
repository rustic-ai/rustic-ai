import asyncio
import os
from typing import Any, Dict, List

from pydantic import BaseModel
import pytest
import shortuuid

from rustic_ai.core import Guild, GuildTopics, Priority
from rustic_ai.core.agents.eip.splitter_agent import (
    FormatSelector,
    FormatSelectorStrategies,
    JsonataSplitter,
    SplitterAgent,
    SplitterConf,
)
from rustic_ai.core.agents.system.models import (
    UserAgentCreationRequest,
    UserAgentCreationResponse,
)
from rustic_ai.core.agents.testutils import ProbeAgent
from rustic_ai.core.agents.utils import UserProxyAgent
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder, RouteBuilder
from rustic_ai.core.guild.metastore import Metastore
from rustic_ai.core.messaging.core.message import (
    AgentTag,
    Message,
    RoutingSlip,
)
from rustic_ai.core.utils import GemstoneGenerator
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.core.utils.jexpr import JExpr


class PurchaseOrderRequest(BaseModel):
    order_id: str
    items: List[Dict[str, Any]]
    customer: str


class ItemProcessingResult(BaseModel):
    order_id: str
    id: int
    quantity: int
    customer: str


class TestSplitterGuild:

    @pytest.fixture
    def routing_slip(self) -> RoutingSlip:

        splitter_results_route = (
            RouteBuilder(AgentTag(name="Purchase Order Splitter"))
            .on_message_format(ItemProcessingResult)
            .set_destination_topics("item_processing_results")
            .set_route_times(-1)
            .build()
        )

        slip = RoutingSlip(
            steps=[splitter_results_route],
        )

        return slip

    @pytest.fixture
    def rgdatabase(self):
        db = "sqlite:///splitter_demo.db"

        if os.path.exists("splitter_demo.db"):
            os.remove("splitter_demo.db")

        Metastore.initialize_engine(db)
        Metastore.get_engine(db)
        Metastore.create_db()
        yield db
        Metastore.drop_db()

    @pytest.fixture
    def splitter_guild(self, routing_slip, rgdatabase):
        splitter_guild_builder = GuildBuilder(
            guild_id=f"splitter_guild{shortuuid.uuid()}",
            guild_name="SplitterGuild",
            guild_description="Demonstrates splitting of messages using SplitterAgent",
        )

        splitter_conf = SplitterConf(
            splitter=JsonataSplitter(
                expression=JExpr(
                    '$map(items, function($v) {$merge([$v, {"order_id": order_id}, {"customer": customer}] ) } )'
                ).serialize()
            ),
            format_selector=FormatSelector(
                strategy=FormatSelectorStrategies.FIXED, fixed_format=get_qualified_class_name(ItemProcessingResult)
            ),
            topics=["item_processing_results"],
        )

        splitter_agent = (
            AgentBuilder(SplitterAgent)
            .set_id("SplitterAgent")
            .set_name("Purchase Order Splitter")
            .set_description("Splits a PurchaseOrderRequest into multiple ItemRequest messages")
            .set_properties(splitter_conf)
            .add_additional_topic("purchase_orders")
            .listen_to_default_topic(False)
            .build_spec()
        )

        splitter_guild_builder.add_agent_spec(splitter_agent)

        splitter_guild = splitter_guild_builder.set_routes(routing_slip).bootstrap(rgdatabase, "dummy_ord")

        yield splitter_guild
        splitter_guild.shutdown()

    @pytest.mark.asyncio
    async def test_splitter_guild(self, splitter_guild: Guild, routing_slip: RoutingSlip, generator: GemstoneGenerator):

        probe_agent: ProbeAgent = (
            AgentBuilder(ProbeAgent)
            .set_id("test_agent")
            .set_name("Test Agent")
            .set_description("A test agent")
            .add_additional_topic(UserProxyAgent.BROADCAST_TOPIC)
            .add_additional_topic(GuildTopics.SYSTEM_TOPIC)
            .add_additional_topic("item_processing_results")
            .build()
        )

        splitter_guild._add_local_agent(probe_agent)

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

        id_obj = generator.get_id(Priority.NORMAL)
        wrapped_message = Message(
            id_obj=id_obj,
            topics="purchase_orders",
            payload=test_order.model_dump(),
            format=get_qualified_class_name(PurchaseOrderRequest),
            sender=AgentTag(id="test_agent", name="TestAgent"),
        )
        probe_agent.publish(
            topic=UserProxyAgent.get_user_inbox_topic("test_user"),
            payload=wrapped_message,
        )

        await asyncio.sleep(10)

        messages = probe_agent.get_messages()[-2:]

        assert messages[0].payload["order_id"] == "PO-12345"
        assert messages[1].payload["order_id"] == "PO-12345"
        assert messages[0].payload["id"] == "item-001"
        assert messages[0].payload["quantity"] == 2
        assert messages[1].payload["id"] == "item-002"
        assert messages[1].payload["quantity"] == 1
