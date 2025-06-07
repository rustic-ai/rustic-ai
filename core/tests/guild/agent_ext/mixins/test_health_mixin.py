from datetime import datetime
import os
import time

import pytest
import shortuuid

from rustic_ai.core.agents.testutils.echo_agent import EchoAgent
from rustic_ai.core.agents.testutils.probe_agent import EssentialProbeAgent
from rustic_ai.core.guild.agent_ext.mixins.health import HealthConstants, Heartbeat
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.guild.dsl import AgentSpec, GuildTopics
from rustic_ai.core.guild.metastore.database import Metastore


class TestHealthMixin:

    @pytest.fixture
    def echo_agent(self) -> AgentSpec:
        name = "EchoAgent"
        description = "An echo agent"
        additional_topic = "echo_topic"
        return (
            AgentBuilder(EchoAgent)
            .set_name(name)
            .set_description(description)
            .add_additional_topic(additional_topic)
            .listen_to_default_topic(False)
            .build_spec()
        )

    @pytest.fixture
    def guild_id(self):
        return f"test_guild_id_{shortuuid.uuid()}"

    @pytest.fixture
    def guild_name(self):
        return "test_guild_name"

    @pytest.fixture
    def guild_description(self, guild_name):
        return f"description for {guild_name}"

    @pytest.fixture
    def database(self):
        db = "sqlite:///test_rustic_app.db"

        if os.path.exists("test_rustic_app.db"):
            os.remove("test_rustic_app.db")

        Metastore.initialize_engine(db)
        Metastore.get_engine(db)
        Metastore.create_db()
        yield db
        Metastore.drop_db()

    def test_health_mixin(self, guild_id, guild_name, guild_description, echo_agent, database, org_id):
        builder = GuildBuilder(guild_id, guild_name, guild_description).add_agent_spec(echo_agent)

        guild = builder.bootstrap(database, org_id)

        probe_agent = (
            AgentBuilder(EssentialProbeAgent)
            .set_id("probe_agent")
            .set_name("ProbeAgent")
            .set_description("A probe agent")
            .add_additional_topic(GuildTopics.SYSTEM_TOPIC)
            .add_additional_topic("default_topic")
            .build()
        )

        guild._add_local_agent(probe_agent)

        heartbeat = Heartbeat(checktime=datetime.now())
        isotime = heartbeat.checktime.isoformat()

        msg_id = probe_agent.publish_dict(
            topic=HealthConstants.HEARTBEAT_TOPIC,
            payload=heartbeat.model_dump(),
            format=Heartbeat,
        ).to_int()

        time.sleep(2)

        messages = probe_agent.get_messages()

        assert len(messages) == 2

        mpair = {msg.sender.name: msg for msg in messages}

        assert "EchoAgent" in mpair
        assert "test_guild_name_manager" in mpair

        echo_message = mpair["EchoAgent"]
        assert echo_message.format == "rustic_ai.core.guild.agent_ext.mixins.health.HeartbeatResponse"
        assert echo_message.in_response_to == msg_id
        assert echo_message.payload["checktime"] == isotime
        assert echo_message.payload["checkstatus"] == "OK"
        assert echo_message.topics == HealthConstants.HEARTBEAT_TOPIC

        manager_message = mpair["test_guild_name_manager"]
        assert manager_message.format == "rustic_ai.core.guild.agent_ext.mixins.health.HeartbeatResponse"
        assert manager_message.in_response_to == msg_id
        assert manager_message.payload["checktime"] == isotime
        assert manager_message.payload["checkstatus"] == "OK"
        assert manager_message.topics == HealthConstants.HEARTBEAT_TOPIC

        probe_agent.clear_messages()

        guild.shutdown()
