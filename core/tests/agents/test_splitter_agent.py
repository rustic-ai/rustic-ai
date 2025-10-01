import asyncio
import os
from typing import Any, Dict, List, Optional

from pydantic import BaseModel
import pytest
import shortuuid

from rustic_ai.core import Guild, GuildTopics, Priority
from rustic_ai.core.agents.eip.splitter_agent import (
    CelFormatSelector,
    CelSplitter,
    DictFormatSelector,
    DictSplitter,
    FixedFormatSelector,
    JsonataFormatSelector,
    JsonataSplitter,
    ListFormatSelector,
    ListSplitter,
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


class PurchaseOrderRequest(BaseModel):
    order_id: str
    items: List[Dict[str, Any]]
    customer: str


class ItemOrderList(BaseModel):
    item1: Dict
    item2: Dict


class ItemProcessingResult(BaseModel):
    id: Optional[str]
    quantity: Optional[int]


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

        slip = RoutingSlip(steps=[splitter_results_route])
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

    @pytest.fixture(
        params=[
            (
                JsonataSplitter(expression="$map(items, function($v) { $v })"),
                JsonataFormatSelector(
                    strategy="jsonata", jsonata_expr=f"'{get_qualified_class_name(ItemProcessingResult)}'"
                ),
            ),
            (
                CelSplitter(expression='items.map(i, {"id": i.id, "quantity": i.quantity})'),
                CelFormatSelector(strategy="cel", expression=f"'{get_qualified_class_name(ItemProcessingResult)}'"),
            ),
            (
                ListSplitter(field_name="items"),
                ListFormatSelector(strategy="list", format_list=[get_qualified_class_name(ItemProcessingResult)] * 2),
            ),
            (
                ListSplitter(field_name="items"),
                FixedFormatSelector(strategy="fixed", fixed_format=get_qualified_class_name(ItemProcessingResult)),
            ),
            (
                DictSplitter(),
                DictFormatSelector(
                    strategy="dict",
                    format_dict={
                        "item1": get_qualified_class_name(ItemProcessingResult),
                        "item2": get_qualified_class_name(ItemProcessingResult),
                    },
                ),
            ),
        ]
    )
    def splitter_and_format(self, request):
        return request.param

    @pytest.fixture
    def splitter_guild(self, splitter_and_format, routing_slip, rgdatabase):
        splitter, format_selector = splitter_and_format

        splitter_guild_builder = GuildBuilder(
            guild_id=f"splitter_guild{shortuuid.uuid()}",
            guild_name="SplitterGuild",
            guild_description="Demonstrates splitting of messages using SplitterAgent",
        )

        splitter_conf = SplitterConf(splitter=splitter, format_selector=format_selector)

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
    async def test_splitter_variants(self, splitter_guild: Guild, splitter_and_format, generator: GemstoneGenerator):

        probe_sepc = (
            AgentBuilder(ProbeAgent)
            .set_id("test_agent")
            .set_name("Test Agent")
            .set_description("A test agent")
            .add_additional_topic(UserProxyAgent.BROADCAST_TOPIC)
            .add_additional_topic(GuildTopics.SYSTEM_TOPIC)
            .add_additional_topic("item_processing_results")
            .build_spec()
        )

        probe_agent: ProbeAgent = splitter_guild._add_local_agent(probe_sepc)

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

        splitter_object, _ = splitter_and_format

        payload: str | dict = {}
        message_format: str = ""
        if isinstance(splitter_object, DictSplitter):
            dict_payload = {"item1": {"id": "item-001", "quantity": 2}, "item2": {"id": "item-002", "quantity": 1}}
            payload = dict_payload
            message_format = get_qualified_class_name(ItemOrderList)
        else:
            payload = test_order.model_dump()
            message_format = get_qualified_class_name(PurchaseOrderRequest)

        id_obj = generator.get_id(Priority.NORMAL)
        wrapped_message = Message(
            id_obj=id_obj,
            topics="purchase_orders",
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
        messages = [msg for msg in messages if msg.topics == "item_processing_results"]
        assert len(messages) > 0
        assert messages[0].payload["id"] == "item-001"
        assert messages[0].payload["quantity"] == 2
