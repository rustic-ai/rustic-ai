import asyncio
import logging
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
from rustic_ai.core.guild.agent import Agent, ProcessContext, processor
from rustic_ai.core.guild.agent_ext.mixins.scheduler import (  # Adjust import paths
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
from rustic_ai.core.utils import GemstoneGenerator
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name


class PingMessage(BaseModel):
    text: str


class PingReply(BaseModel):
    pings: List[str]


class DummySchedulerAgent(Agent):
    def __init__(self):
        self.received_pings = []

    @processor(PingMessage)
    def handle_ping(self, ctx: ProcessContext[PingMessage]):
        logging.info(f"[DummySchedulerAgent] Received ping: {ctx.payload.text}")
        self.received_pings.append(ctx.payload.text)

        ctx.send(PingReply(pings=self.received_pings))


class TestSchedulerMixin:

    @pytest.fixture
    def routing_slip(self) -> RoutingSlip:

        slip = RoutingSlip(steps=[])
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
    def scheduler_guild(routing_slip, rgdatabase):
        builder = GuildBuilder(
            guild_id=f"scheduler_guild_{shortuuid.uuid()}",
            guild_name="Scheduler Test Guild",
            guild_description="Tests scheduling messages to self",
        )

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
        # builder.set_routes(routing_slip)

        guild = builder.bootstrap(rgdatabase, "dummy_user")
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
            .build_spec()
        )

        probe_agent: ProbeAgent = scheduler_guild._add_local_agent(probe_sepc)

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

        msg = ScheduleOnceMessage(
            key=shortuuid.uuid(),
            delay_seconds=2.0,
            mesage_payload={"text": "Ping after delay!"},
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

        messages = probe_agent.get_messages()
        assert len(messages) > 0
        assert messages[0].payload["id"] == "item-001"
        assert messages[0].payload["quantity"] == 2
