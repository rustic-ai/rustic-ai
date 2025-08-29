import os
import time

from flaky import flaky
import pytest

from rustic_ai.core import GuildTopics, MessageTrackingClient, MessagingConfig
from rustic_ai.core.agents.system.models import StopGuildRequest
from rustic_ai.core.agents.testutils import EchoAgent
from rustic_ai.core.agents.testutils.probe_agent import ProbeAgent
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
    def messaging(self, messaging_server):
        # Use the shared messaging server from conftest.py instead of auto-starting
        server, port = messaging_server
        return MessagingConfig(
            backend_module="rustic_ai.core.messaging.backend.embedded_backend",
            backend_class="EmbeddedMessagingBackend",
            backend_config={"auto_start_server": False, "port": port},
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

    @pytest.mark.xfail(reason="Flaky test, needs investigation")
    @flaky(max_runs=3, min_passes=1)
    def test_guild_shutdown(self, messaging: MessagingConfig, probe_spec, database, org_id):

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

        time.sleep(1.0)  # Increased wait time to allow GuildManagerAgent to launch EchoAgent
        running_agents = guild.execution_engine.get_agents_in_guild(guild_id)
        assert len(running_agents) >= 2

        probe_agent: ProbeAgent = guild._add_local_agent(probe_spec)  # type: ignore

        probe_agent.publish_dict(
            topic=GuildTopics.SYSTEM_TOPIC,
            payload=StopGuildRequest(guild_id=guild.id, user_id="test_user_id").model_dump(),
            format=StopGuildRequest,
        )

        is_agent_running = guild.execution_engine.is_agent_running(guild_id, echo_agent.id)

        loop_count = 0
        while is_agent_running and loop_count < 10:
            time.sleep(1)
            is_agent_running = guild.execution_engine.is_agent_running(guild_id, echo_agent.id)
            loop_count += 1

        assert is_agent_running is False

        time.sleep(1)

        engine = Metastore.get_engine(database)
        guild_store = GuildStore(engine)
        guild_model = guild_store.get_guild(guild_id)
        assert guild_model is not None

        loop_count = 0
        while guild_model.status != "stopped" and loop_count < 10:
            time.sleep(0.5)
            guild_model = guild_store.get_guild(guild_id)
            assert guild_model is not None
            loop_count += 1

        assert guild_model.status == "stopped"
