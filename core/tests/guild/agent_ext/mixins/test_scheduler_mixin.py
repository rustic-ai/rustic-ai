import asyncio
import os
from typing import List

from pydantic import BaseModel
import pytest
import shortuuid

from rustic_ai.core import Guild, GuildTopics, Priority
from rustic_ai.core.agents.system.models import (
    UserAgentCreationRequest,
    UserAgentCreationResponse,
)
from rustic_ai.core.agents.testutils import ProbeAgent
from rustic_ai.core.agents.utils import UserProxyAgent
from rustic_ai.core.guild import agent
from rustic_ai.core.guild.agent import Agent, ProcessContext
from rustic_ai.core.guild.agent_ext.mixins.scheduler import (
    CancelScheduledJobMessage,
    ScheduleFixedRateMessage,
    ScheduleOnceMessage,
    SchedulerMixin,
)
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder, RouteBuilder
from rustic_ai.core.guild.metastore import Metastore
from rustic_ai.core.messaging.core.message import (
    AgentTag,
    Message,
    RoutingSlip,
)
from rustic_ai.core.messaging.core.messaging_config import MessagingConfig
from rustic_ai.core.utils import GemstoneGenerator
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name


class PingMessage(BaseModel):
    text: str


class PingReply(BaseModel):
    pings: List[str]


class DummySchedulerAgent(Agent, SchedulerMixin):
    def __init__(self):
        self.received_pings = []
        self.set_default_reason("Dummy Agent action")

    @agent.processor(PingMessage, handle_essential=True)
    def handle_ping(self, ctx: ProcessContext[PingMessage]):
        print(f"[DummySchedulerAgent] Received ping: {ctx.payload.text}")
        self.received_pings.append(ctx.payload.text)

        ctx.send(PingReply(pings=self.received_pings), reason="pings scheduled and received")


class TestSchedulerMixin:

    @pytest.fixture
    def messaging_config(self):
        return MessagingConfig(
            backend_module="rustic_ai.redis.messaging.backend",
            backend_class="RedisMessagingBackend",
            backend_config={"redis_client": {"host": "localhost", "port": 6379}},
        )

    @pytest.fixture
    def routing_slip(self) -> RoutingSlip:
        dummy_to_final = (
            RouteBuilder(AgentTag(name="Scheduler Agent"))
            .on_message_format(PingReply)
            .set_destination_topics("final_topic")
            .set_route_times(-1)
            .build()
        )
        slip = RoutingSlip(steps=[dummy_to_final])
        return slip

    @pytest.fixture
    def rgdatabase(self):
        db = "sqlite:///scheduler_test.db"

        if os.path.exists("scheduler_test.db"):
            os.remove("scheduler_test.db")

        Metastore.initialize_engine(db)
        Metastore.get_engine(db)
        Metastore.create_db()
        yield db
        Metastore.drop_db()

    @pytest.fixture
    def scheduler_guild(self, routing_slip, rgdatabase, messaging_config):
        builder = GuildBuilder(
            guild_id=f"scheduler_guild_{shortuuid.uuid()}",
            guild_name="Scheduler Test Guild",
            guild_description="Tests scheduling messages to self",
        )

        builder.set_property("messaging", messaging_config)

        agent_spec = (
            AgentBuilder(DummySchedulerAgent)
            .set_id("scheduler_agent")
            .set_name("Scheduler Agent")
            .set_description("An agent that tests SchedulerMixin")
            .add_additional_topic("scheduler")
            .add_additional_topic(GuildTopics.SYSTEM_TOPIC)
            .build_spec()
        )

        builder.add_agent_spec(agent_spec)
        guild = builder.set_routes(routing_slip).bootstrap(rgdatabase, "dummy_ord")

        yield guild
        guild.shutdown()

    @pytest.mark.asyncio
    async def test_schedule_once(self, scheduler_guild: Guild, generator: GemstoneGenerator):
        probe_sepc = (
            AgentBuilder(ProbeAgent)
            .set_id("test_agent")
            .set_name("Test Agent")
            .set_description("A test agent")
            .add_additional_topic(UserProxyAgent.BROADCAST_TOPIC)
            .add_additional_topic(GuildTopics.SYSTEM_TOPIC)
            .add_additional_topic("final_topic")
            .build_spec()
        )

        probe_agent: ProbeAgent = scheduler_guild._add_local_agent(probe_sepc)

        probe_agent.publish_dict(
            topic=GuildTopics.SYSTEM_TOPIC,
            payload=UserAgentCreationRequest(user_id="test_user", user_name="test_user").model_dump(),
            format=UserAgentCreationRequest,
        )

        await asyncio.sleep(5)

        system_messages = probe_agent.get_messages()
        assert len(system_messages) == 1

        user_created = system_messages[0]
        assert user_created.format == get_qualified_class_name(UserAgentCreationResponse)
        assert user_created.payload["user_id"] == "test_user"
        assert user_created.payload["status_code"] == 201

        probe_agent.clear_messages()

        msg = ScheduleOnceMessage(
            key=shortuuid.uuid(),
            delay_seconds=2.0,
            mesage_payload={"text": "Ping after delay!"},
            message_format=get_qualified_class_name(PingMessage),
        ).model_dump()

        id_obj = generator.get_id(Priority.NORMAL)
        wrapped_message = Message(
            id_obj=id_obj,
            topics="scheduler",
            payload=msg,
            format=get_qualified_class_name(ScheduleOnceMessage),
            sender=AgentTag(id="test_agent", name="TestAgent"),
        )
        probe_agent.publish(
            topic=UserProxyAgent.get_user_inbox_topic("test_user"),
            payload=wrapped_message,
        )

        await asyncio.sleep(10)

        msging = probe_agent._client._messaging

        self_messages = msging.get_messages_for_topic_since(
            GuildTopics.get_self_agent_inbox("scheduler_agent"),
            0,
        )

        assert self_messages[-1].payload["text"] == "Ping after delay!"

        all_messages = probe_agent.get_messages()
        assert all_messages[-1].format == get_qualified_class_name(PingReply)

        response = PingReply.model_validate(all_messages[-1].payload)
        assert len(response.pings) == 1
        assert response.pings[0] == "Ping after delay!"
        assert all_messages[-1].reason == "pings scheduled and received"

        probe_agent.clear_messages()

        # --- Test ScheduleFixedRateMessage ---

        fixed_key = shortuuid.uuid()
        fixed_msg = ScheduleFixedRateMessage(
            key=fixed_key,
            interval_seconds=1.0,
            mesage_payload={"text": "Repeated ping!"},
            message_format=get_qualified_class_name(PingMessage),
        ).model_dump()

        wrapped_fixed = Message(
            id_obj=generator.get_id(Priority.NORMAL),
            topics="scheduler",
            payload=fixed_msg,
            format=get_qualified_class_name(ScheduleFixedRateMessage),
            sender=AgentTag(id="test_agent", name="TestAgent"),
        )
        probe_agent.publish(
            topic=UserProxyAgent.get_user_inbox_topic("test_user"),
            payload=wrapped_fixed,
        )

        await asyncio.sleep(3.5)  # Let it fire ~3 times

        all_messages = probe_agent.get_messages()

        assert len(all_messages) >= 2
        assert all_messages[-1].format == get_qualified_class_name(PingReply)

        response = PingReply.model_validate(all_messages[-1].payload)
        assert len(response.pings) >= 2
        assert response.pings[-1] == "Repeated ping!"

        probe_agent.clear_messages()

        # --- Test CancelScheduledJobMessage ---

        cancel_msg = CancelScheduledJobMessage(key=fixed_key).model_dump()
        wrapped_cancel = Message(
            id_obj=generator.get_id(Priority.NORMAL),
            topics="scheduler",
            payload=cancel_msg,
            format=get_qualified_class_name(CancelScheduledJobMessage),
            sender=AgentTag(id="test_agent", name="TestAgent"),
        )
        probe_agent.publish(
            topic=UserProxyAgent.get_user_inbox_topic("test_user"),
            payload=wrapped_cancel,
        )

        await asyncio.sleep(4)  # Give time to ensure it's cancelled

        all_messages = probe_agent.get_messages()

        after_cancel = [m for m in all_messages if m.payload.get("text") == "Repeated ping!"]
        assert len(after_cancel) == 0  # no more repeats after cancel
