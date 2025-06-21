import os
import time

import pytest

from rustic_ai.core import GuildTopics, MessageTrackingClient, MessagingConfig
from rustic_ai.core.agents.system.models import StopGuildRequest
from rustic_ai.core.agents.testutils import EchoAgent, ProbeAgent
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.guild.metastore import GuildStore, Metastore
from rustic_ai.core.messaging.core.message import (
    AgentTag,
    RoutingDestination,
    RoutingRule,
    RoutingSlip,
)


class TestGuildStop:

    @pytest.fixture
    def messaging(self):

        return MessagingConfig(
            backend_module="rustic_ai.core.messaging.backend",
            backend_class="InMemoryMessagingBackend",
            backend_config={},
        )

    @pytest.fixture
    def database(self):
        db = "sqlite:///test_rustic_guild_stop.db"

        if os.path.exists("test_rustic_guild_stop.db"):
            os.remove("test_rustic_guild_stop.db")

        Metastore.initialize_engine(db)
        Metastore.get_engine(db)
        Metastore.create_db()
        yield db
        Metastore.drop_db()

    def test_guild_bootstrap(self, messaging: MessagingConfig, probe_agent: ProbeAgent, database, org_id):

        guild_id = "guild_stop_test"
        guild_name = "Guild1"
        guild_description = "Guild for testing stop functionality"

        echo_agent = (
            AgentBuilder(EchoAgent)
            .set_name("EchoAgent")
            .set_description("An echo agent")
            .add_additional_topic("echo_topic")
            .listen_to_default_topic(False)
            .build_spec()
        )

        routing_slip = RoutingSlip(
            steps=[
                RoutingRule(
                    agent=AgentTag(name=echo_agent.name),
                    destination=RoutingDestination(
                        topics=GuildTopics.DEFAULT_TOPICS[0],
                    ),
                )
            ]
        )

        builder = (
            GuildBuilder(guild_id, guild_name, guild_description)
            .add_agent_spec(echo_agent)
            .set_property("client_type", MessageTrackingClient.get_qualified_class_name())
            .set_routes(routing_slip)
            .set_messaging(
                messaging.backend_module,
                messaging.backend_class,
                messaging.backend_config,
            )
        )

        guild = builder.bootstrap(database, org_id)

        time.sleep(2)
        running_agents = guild.execution_engine.get_agents_in_guild(guild_id)
        assert len(running_agents) == 2

        guild._add_local_agent(probe_agent)

        probe_agent.publish_dict(
            topic=GuildTopics.SYSTEM_TOPIC,
            payload=StopGuildRequest(guild_id=guild.id).model_dump(),
            format=StopGuildRequest,
        )

        time.sleep(2)

        is_agent_running = guild.execution_engine.is_agent_running(guild_id, echo_agent.id)
        assert is_agent_running is False

        engine = Metastore.get_engine(database)
        guild_store = GuildStore(engine)
        guild_model = guild_store.get_guild(guild_id)
        assert guild_model is not None
        assert guild_model.status == "stopped"
