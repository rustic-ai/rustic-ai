import importlib
import time

import pytest
import shortuuid
from sqlmodel import Session

from rustic_ai.core.agents.system.guild_manager_agent import (
    AgentGetRequest,
    AgentInfoResponse,
    AgentLaunchRequest,
    AgentLaunchResponse,
    AgentListRequest,
    BadInputResponse,
    GuildManagerAgent,
    RunningAgentListRequest,
    UserAgentCreationRequest,
    UserAgentCreationResponse,
)
from rustic_ai.core.agents.system.models import AgentListResponse, ConflictResponse
from rustic_ai.core.agents.testutils.echo_agent import EchoAgent
from rustic_ai.core.agents.testutils.probe_agent import ProbeAgent
from rustic_ai.core.agents.utils.user_proxy_agent import UserProxyAgent
from rustic_ai.core.guild import GSKC, AgentSpec
from rustic_ai.core.guild.agent_ext.mixins.health import HealthConstants
from rustic_ai.core.guild.builders import (
    AgentBuilder,
    GuildBuilder,
    GuildHelper,
    RouteBuilder,
)
from rustic_ai.core.guild.dsl import GuildTopics
from rustic_ai.core.guild.metastore.database import Metastore
from rustic_ai.core.guild.metastore.guild_store import GuildStore
from rustic_ai.core.guild.metastore.models import GuildModel
from rustic_ai.core.messaging import Message, MessagingConfig
from rustic_ai.core.messaging.client.message_tracking_client import (
    MessageTrackingClient,
)
from rustic_ai.core.messaging.core.message import (
    AgentTag,
    MessageConstants,
    RoutingDestination,
    RoutingRule,
    RoutingSlip,
)
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.core.utils.gemstone_id import GemstoneGenerator
from rustic_ai.core.utils.priority import Priority

from .simple_agent import SimpleAgent


class TestGuildBuilder:

    exec_engine_clz: str = "rustic_ai.core.guild.execution.sync.sync_exec_@engine.SyncExecutionEngine"

    @pytest.fixture(
        scope="function",  # Changed from class to function to access messaging_server
        params=[
            pytest.param(
                "InMemoryMessagingBackend",
                id="InMemoryMessagingBackend",
            ),
            pytest.param(
                "EmbeddedMessagingBackend",
                id="EmbeddedMessagingBackend",
            ),
        ],
    )
    def messaging(self, request, messaging_server) -> MessagingConfig:
        backend_type = request.param

        if backend_type == "InMemoryMessagingBackend":
            return MessagingConfig(
                backend_module="rustic_ai.core.messaging.backend",
                backend_class="InMemoryMessagingBackend",
                backend_config={},
            )
        elif backend_type == "EmbeddedMessagingBackend":
            # Use the shared messaging server from conftest.py
            server, port = messaging_server
            return MessagingConfig(
                backend_module="rustic_ai.core.messaging.backend.embedded_backend",
                backend_class="EmbeddedMessagingBackend",
                backend_config={"auto_start_server": False, "port": port},
            )
        else:
            raise ValueError(f"Unknown backend type: {backend_type}")

    @pytest.fixture
    def agent_spec(self) -> AgentSpec:
        name = "Simple Agent"
        description = "A simple agent"

        return AgentBuilder(SimpleAgent).set_name(name).set_description(description).build_spec()

    @pytest.fixture
    def echo_agent(self) -> AgentSpec:
        name = "EchoAgent"
        description = "An echo agent"
        additional_topic = "echo_topic"
        return (
            AgentBuilder(EchoAgent)
            .set_name(name)
            .set_id("echo001")
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

    # Removed duplicate database fixture - using the one from conftest.py instead
    # This ensures each test gets a unique database file with proper cleanup

    def test_initialization(self, guild_id, guild_name, guild_description):
        spec = GuildBuilder(guild_id, guild_name, guild_description).build_spec()

        assert spec.id == guild_id
        assert spec.name == guild_name
        assert spec.description == guild_description

    def test_setting_client_type(self, guild_id, guild_name, guild_description):
        spec_builder = GuildBuilder(guild_id, guild_name, guild_description)
        spec_builder.set_property("client_type", MessageTrackingClient)
        spec = spec_builder.build_spec()

        assert spec.id == guild_id
        assert spec.name == guild_name
        assert spec.description == guild_description
        assert spec.properties["client_type"] == MessageTrackingClient

    def test_initialization_with_messaging_config(
        self, guild_id, guild_name, guild_description, messaging: MessagingConfig
    ):
        messaging_config = messaging

        builder = GuildBuilder(guild_id, guild_name, guild_description)
        builder = builder.set_messaging(
            messaging_config.backend_module,
            messaging_config.backend_class,
            messaging_config.backend_config,
        )

        spec = builder.build_spec()

        assert spec.properties[GSKC.MESSAGING][GSKC.BACKEND_MODULE] == messaging_config.backend_module
        assert spec.properties[GSKC.MESSAGING][GSKC.BACKEND_CLASS] == messaging_config.backend_class
        assert spec.properties[GSKC.MESSAGING][GSKC.BACKEND_CONFIG] == messaging_config.backend_config

    def test_empty_initialization(self, guild_id, guild_name, guild_description):
        spec = (
            GuildBuilder(guild_id)
            .set_name(guild_name)
            .set_description(guild_description)
            .set_property("test_prop", "something")
            .build_spec()
        )

        assert spec.id == guild_id
        assert spec.name == guild_name
        assert spec.description == guild_description
        assert spec.properties["test_prop"] == "something"

    def test_set_description(self, guild_id, guild_name, guild_description):
        spec = GuildBuilder(guild_id, guild_name).set_description(guild_description).build_spec()
        assert spec.description == guild_description

    def test_add_agent(self, agent_spec, guild_id, guild_name, guild_description):
        spec = GuildBuilder(guild_id, guild_name, guild_description).add_agent_spec(agent_spec).build_spec()
        assert agent_spec in spec.agents

    def test_set_execution_engine(self, guild_id, guild_name, guild_description):
        spec = (
            GuildBuilder(guild_id, guild_name, guild_description)
            .set_execution_engine(self.exec_engine_clz)
            .build_spec()
        )
        assert spec.properties[GSKC.EXECUTION_ENGINE] == self.exec_engine_clz

    def test_set_messaging(self, guild_id, guild_name, guild_description, messaging: MessagingConfig):
        backend_module = messaging.backend_module
        backend_class = messaging.backend_class
        backend_config: dict = messaging.backend_config

        spec = (
            GuildBuilder(guild_id, guild_name, guild_description)
            .set_messaging(backend_module, backend_class, backend_config)
            .build_spec()
        )

        assert spec.properties[GSKC.MESSAGING][GSKC.BACKEND_MODULE] == backend_module
        assert spec.properties[GSKC.MESSAGING][GSKC.BACKEND_CLASS] == backend_class
        assert spec.properties[GSKC.MESSAGING][GSKC.BACKEND_CONFIG] == backend_config

    def test_guild_launch(self, agent_spec, guild_id, guild_name, guild_description, org_id):
        builder = GuildBuilder(guild_id, guild_name, guild_description).add_agent_spec(agent_spec)
        guild = builder.launch(organization_id=org_id)
        assert guild.id == guild_id
        assert guild.name == guild_name
        assert guild.get_agent(agent_spec.id) == agent_spec

    def test_guild_load(self, agent_spec, guild_id, guild_name, guild_description, org_id):
        builder = GuildBuilder(guild_id, guild_name, guild_description).add_agent_spec(agent_spec)
        guild = builder.load(organization_id=org_id)
        assert guild.id == guild_id
        assert guild.name == guild_name
        assert guild.get_agent(agent_spec.id) == agent_spec

    def test_agent_spec(self):
        name = "Simple Agent"
        description = "A simple agent"

        agent_spec: AgentSpec = (
            AgentBuilder(SimpleAgent)
            .set_name(name)
            .set_description(description)
            .add_additional_topic("test_topic")
            .build_spec()
        )

        assert agent_spec.name == name
        assert agent_spec.description == description
        assert agent_spec.class_name == SimpleAgent.get_qualified_class_name()
        assert agent_spec.additional_topics == ["test_topic"]

    def test_guild_spec_required_fields(self):
        with pytest.raises(ValueError):
            GuildBuilder().build_spec()

    def test_agent_spec_required_fields(self):
        with pytest.raises(ValueError):
            AgentBuilder(SimpleAgent).build_spec()

    def test_guild_from_json(
        self,
        agent_spec: AgentSpec,
        guild_id: str,
        guild_name: str,
        guild_description: str,
    ):
        json_path = importlib.resources.files("core.tests.resources.guild_specs").joinpath("test_guild.json")
        new_spec = GuildBuilder.from_json_file(json_path).build_spec()

        assert new_spec.name == guild_name
        assert new_spec.description == guild_description
        assert new_spec.agents[0].name == agent_spec.name
        assert new_spec.agents[0].description == agent_spec.description
        assert new_spec.agents[0].class_name == agent_spec.class_name
        assert new_spec.agents[0].additional_topics == agent_spec.additional_topics
        assert new_spec.agents[0].properties == agent_spec.properties

        msgconf = GuildHelper.get_messaging_config(new_spec)

        # This is not parameterized as we are testing initialization from a JSON file
        assert msgconf.backend_module == "rustic_ai.core.messaging.backend.embedded_backend"
        assert msgconf.backend_class == "EmbeddedMessagingBackend"
        assert msgconf.backend_config == {"auto_start_server": True}

    def test_guild_from_yaml(
        self,
        agent_spec: AgentSpec,
        guild_id: str,
        guild_name: str,
        guild_description: str,
    ):
        yaml_path = importlib.resources.files("core.tests.resources.guild_specs").joinpath("test_guild.yaml")  # type: ignore
        new_spec = GuildBuilder.from_yaml_file(yaml_path).build_spec()

        assert new_spec.name == guild_name
        assert new_spec.description == guild_description
        assert new_spec.agents[0].name == agent_spec.name
        assert new_spec.agents[0].description == agent_spec.description
        assert new_spec.agents[0].class_name == agent_spec.class_name
        assert new_spec.agents[0].additional_topics == agent_spec.additional_topics
        assert new_spec.agents[0].properties == agent_spec.properties

        msgconf = GuildHelper.get_messaging_config(new_spec)

        # This is not parameterized as we are testing initialization from a YAML file
        assert msgconf.backend_module == "rustic_ai.core.messaging.backend.embedded_backend"
        assert msgconf.backend_class == "EmbeddedMessagingBackend"
        assert msgconf.backend_config == {}

    def test_guild_bootstrap(
        self,
        agent_spec,
        echo_agent: AgentSpec,
        guild_id,
        guild_name,
        guild_description,
        messaging: MessagingConfig,
        database,
        org_id,
    ):

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

        engine = Metastore.get_engine(database)

        guild = builder.bootstrap(database, org_id)
        assert guild.id == guild_id
        assert guild.name == guild_name

        assert guild.messaging.backend_module == messaging.backend_module
        assert guild.messaging.backend_class == messaging.backend_class
        assert guild.messaging.backend_config == messaging.backend_config

        guild_manager = guild.list_agents()[0]
        assert guild_manager.class_name == get_qualified_class_name(GuildManagerAgent)

        assert guild.routes == routing_slip

        time.sleep(0.5)  # Increased wait time for EmbeddedMessagingBackend
        manager_name = f"GuildManagerAgent4{guild_id}"

        # Test if the echo agent is added to the metastore
        with Session(engine) as session:
            guild_model = GuildModel.get_by_id(session, guild_id)
            assert guild_model, f"Guild with id {guild_id} not found in the database"
            agents = guild_model.agents
            assert len(agents) == 2
            agent_names = [agent.name for agent in agents]
            agent_classes = [agent.class_name for agent in agents]

            assert "EchoAgent" in agent_names
            assert "rustic_ai.core.agents.testutils.echo_agent.EchoAgent" in agent_classes

            assert manager_name in agent_names
            assert get_qualified_class_name(GuildManagerAgent) in agent_classes

        guild_store = GuildStore(engine)
        guild_model = guild_store.get_guild(guild_id)

        assert guild_model

        guild_spec = guild_model.to_guild_spec()

        assert guild_spec
        assert guild_spec.id == guild_id
        assert guild_spec.name == guild_name
        assert guild_spec.description == guild_description
        assert guild_spec.routes == routing_slip

        agent_specs = guild_spec.agents

        assert len(agent_specs) == 2

        echo_agent_spec = agent_specs[0]
        assert echo_agent_spec.name == "EchoAgent"
        assert echo_agent_spec.class_name == get_qualified_class_name(EchoAgent)
        assert echo_agent_spec.additional_topics == ["echo_topic"]
        assert echo_agent_spec.properties.model_dump() == {}
        assert echo_agent_spec.listen_to_default_topic is False
        assert echo_agent_spec.act_only_when_tagged is False

        guild_manager_agent_spec = agent_specs[1]
        assert guild_manager_agent_spec.name == manager_name
        assert guild_manager_agent_spec.class_name == get_qualified_class_name(GuildManagerAgent)
        assert guild_manager_agent_spec.additional_topics == [
            GuildTopics.SYSTEM_TOPIC,
            HealthConstants.HEARTBEAT_TOPIC,
            GuildTopics.GUILD_STATUS_TOPIC,
        ]
        assert guild_manager_agent_spec.properties
        assert guild_manager_agent_spec.listen_to_default_topic is False
        assert guild_manager_agent_spec.act_only_when_tagged is False

        probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id("probe_agent")
            .set_name("ProbeAgent")
            .set_description("A probe agent")
            .add_additional_topic(GuildTopics.SYSTEM_TOPIC)
            .add_additional_topic("echo_topic")
            .build_spec()
        )

        probe_agent: ProbeAgent = guild._add_local_agent(probe_spec)  # type: ignore

        # Test the GuildManagerAgent was launched correctly and has launched the EchoAgent
        probe_agent.publish_dict(
            topic=GuildTopics.SYSTEM_TOPIC,
            payload=AgentListRequest(guild_id=guild.id).model_dump(),
            format=AgentListRequest,
        )

        time.sleep(1.0)  # Increased wait time to allow GuildManagerAgent to respond

        probe_agent_messages = probe_agent.get_messages()
        assert len(probe_agent_messages) == 1
        agent_list_response = AgentListResponse.model_validate(probe_agent_messages[0].payload)
        assert agent_list_response.agents[0].name == "EchoAgent"
        assert agent_list_response.agents[0].class_name == get_qualified_class_name(EchoAgent)

        # Test the EchoAgent was launched correctly
        probe_agent.publish_dict(
            topic="echo_topic",
            payload={"message": "Hello, world!"},
            routing_slip=guild.routes,
        )

        time.sleep(0.01)

        probe_agent_messages = probe_agent.get_messages()
        assert len(probe_agent_messages) == 2

        echoed_msg = probe_agent_messages[1]
        echo_response = echoed_msg.payload

        assert echo_response["message"] == "Hello, world!"
        assert echoed_msg.topics == GuildTopics.DEFAULT_TOPICS[0]
        assert echoed_msg.sender.name == "EchoAgent"

        # Test a new agent can be launched by the GuildManagerAgent
        probe_agent.publish_dict(
            topic=GuildTopics.SYSTEM_TOPIC,
            payload=AgentLaunchRequest(agent_spec=agent_spec).model_dump(),
            format=AgentLaunchRequest,
        )

        time.sleep(1.0)  # Increased sleep time for EmbeddedMessagingBackend

        probe_agent_messages = probe_agent.get_messages()
        assert len(probe_agent_messages) == 3

        agent_launch_response = AgentLaunchResponse.model_validate(probe_agent_messages[2].payload)

        assert agent_launch_response.agent_id
        assert agent_launch_response.status_code == 201
        assert agent_launch_response.status == "Agent launched successfully"

        probe_agent.clear_messages()

        # Test that the new agent can be fetched from the GuildManagerAgent
        probe_agent.publish_dict(
            topic=GuildTopics.SYSTEM_TOPIC,
            payload=AgentGetRequest(guild_id=guild.id, agent_id=agent_launch_response.agent_id).model_dump(),
            format=AgentGetRequest,
        )

        time.sleep(0.01)

        probe_agent_messages = probe_agent.get_messages()
        assert len(probe_agent_messages) == 1

        assert probe_agent_messages[0].format == get_qualified_class_name(AgentInfoResponse)
        agent_get_response = probe_agent_messages[0].payload

        assert agent_get_response["name"] == "Simple Agent"
        assert agent_get_response["class_name"] == get_qualified_class_name(SimpleAgent)

        probe_agent.clear_messages()

        probe_agent.publish_dict(
            topic=GuildTopics.SYSTEM_TOPIC,
            payload=AgentListRequest(guild_id="wrong_id").model_dump(),
            format=AgentListRequest,
        )

        time.sleep(0.01)

        probe_agent_messages = probe_agent.get_messages()
        assert len(probe_agent_messages) == 1

        agent_list_response = BadInputResponse.model_validate(probe_agent_messages[0].payload)

        assert agent_list_response.status_code == 400
        assert agent_list_response.status == "Bad Request"
        assert agent_list_response.message == "Invalid guild id: wrong_id"

    def test_user_proxy_agent(
        self,
        echo_agent: AgentSpec,
        guild_id,
        guild_name,
        guild_description,
        messaging: MessagingConfig,
        database,
        org_id,
    ):
        builder = (
            GuildBuilder(guild_id, guild_name, guild_description)
            .add_agent_spec(echo_agent)
            .set_messaging(
                messaging.backend_module,
                messaging.backend_class,
                messaging.backend_config,
            )
        )

        rule1 = (
            RouteBuilder(echo_agent).set_destination_topics(UserProxyAgent.get_user_outbox_topic("test_user")).build()
        )

        routing_slip = RoutingSlip(steps=[rule1])

        builder.set_routes(routing_slip)

        engine = Metastore.get_engine(database)

        guild = builder.bootstrap(database, org_id)

        time.sleep(0.5)
        manager_name = f"GuildManagerAgent4{guild_id}"

        with Session(engine) as session:
            guild_model = GuildModel.get_by_id(session, guild_id)

            assert guild_model
            g2s = guild_model.to_guild_spec()

            assert g2s.name == guild_name
            assert g2s.description == guild_description

            agents = g2s.agents

            assert len(agents) == 2

            agent_specs = {agent.name: agent for agent in agents}

            echo_agent_spec = agent_specs["EchoAgent"]
            assert echo_agent_spec.name == "EchoAgent"
            assert echo_agent_spec.class_name == get_qualified_class_name(EchoAgent)
            assert echo_agent_spec.additional_topics == ["echo_topic"]
            assert echo_agent_spec.properties.model_dump() == {}
            assert echo_agent_spec.listen_to_default_topic is False
            assert echo_agent_spec.act_only_when_tagged is False

            guild_manager_agent_spec = agent_specs[manager_name]
            assert guild_manager_agent_spec.name == manager_name
            assert guild_manager_agent_spec.class_name == get_qualified_class_name(GuildManagerAgent)
            assert guild_manager_agent_spec.additional_topics == [
                GuildTopics.SYSTEM_TOPIC,
                HealthConstants.HEARTBEAT_TOPIC,
                GuildTopics.GUILD_STATUS_TOPIC,
            ]
            assert guild_manager_agent_spec.properties
            assert guild_manager_agent_spec.listen_to_default_topic is False
            assert guild_manager_agent_spec.act_only_when_tagged is False

            assert g2s.properties[GSKC.MESSAGING][GSKC.BACKEND_MODULE] == messaging.backend_module
            assert g2s.properties[GSKC.MESSAGING][GSKC.BACKEND_CLASS] == messaging.backend_class
            assert g2s.properties[GSKC.MESSAGING][GSKC.BACKEND_CONFIG] == messaging.backend_config

        user_topic = UserProxyAgent.get_user_inbox_topic("test_user")
        user_message_topic = UserProxyAgent.get_user_notifications_topic("test_user")
        user_message_forward_topic = "user_message_forward:test_user"
        user_outbox_topic = UserProxyAgent.get_user_outbox_topic("test_user")
        user_system_notification_topic = UserProxyAgent.get_user_system_notifications_topic("test_user")

        probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id("probe_agent")
            .set_name("ProbeAgent")
            .set_description("A probe agent")
            .add_additional_topic(GuildTopics.SYSTEM_TOPIC)
            .add_additional_topic(user_topic)
            .add_additional_topic(user_message_topic)
            .add_additional_topic(user_message_forward_topic)
            .add_additional_topic(user_outbox_topic)
            .add_additional_topic(user_system_notification_topic)
            .add_additional_topic("echo_topic")
            .add_additional_topic("default_topic")
            .build_spec()
        )

        probe_agent: ProbeAgent = guild._add_local_agent(probe_spec)  # type: ignore

        probe_agent.publish_dict(
            topic=GuildTopics.SYSTEM_TOPIC,
            payload=UserAgentCreationRequest(user_id="test_user", user_name="test_user").model_dump(),
            format=UserAgentCreationRequest,
        )

        time.sleep(1.0)  # Increased sleep time for EmbeddedMessagingBackend

        probe_agent_messages = probe_agent.get_messages()

        assert len(probe_agent_messages) >= 2

        only_user_agent_creation_response = [
            message
            for message in probe_agent_messages
            if message.format == get_qualified_class_name(UserAgentCreationResponse)
        ]

        assert len(only_user_agent_creation_response) == 1

        user_agent_creation_response = UserAgentCreationResponse.model_validate(
            only_user_agent_creation_response[0].payload
        )

        assert user_agent_creation_response.user_id == "test_user"
        assert user_agent_creation_response.agent_id
        assert user_agent_creation_response.status_code == 201
        assert user_agent_creation_response.status == "Agent created successfully"
        assert user_agent_creation_response.topic == "user:test_user"

        probe_agent.clear_messages()

        # Send a request to get all running agents
        probe_agent.publish_dict(
            topic=GuildTopics.SYSTEM_TOPIC,
            payload=RunningAgentListRequest(guild_id=guild.id).model_dump(),
            format=RunningAgentListRequest,
        )

        time.sleep(0.01)

        probe_agent_messages = probe_agent.get_messages()

        assert len(probe_agent_messages) == 1

        running_agents_response = AgentListResponse.model_validate(probe_agent_messages[0].payload)

        assert len(running_agents_response.agents) == 4

        agent_names = [agent.name for agent in running_agents_response.agents]
        agent_names.sort()

        assert sorted(agent_names) == sorted(
            [
                "EchoAgent",
                "ProbeAgent",
                manager_name,
                "test_user",
            ]
        )

        probe_agent.clear_messages()
        # Test that the UserProxyAgent will forwards wrapped messages
        gemgen = GemstoneGenerator(100)
        wrapped_message = Message(
            id_obj=gemgen.get_id(Priority.NORMAL),
            topics="echo_topic",
            sender=AgentTag(id="dummyUserId", name="dummy_user"),
            payload={"message": "Hello, world! @EchoAgent"},
        )

        probe_agent.publish_dict(
            topic=user_topic,
            payload=wrapped_message.model_dump(),
            format=Message,
        )

        time.sleep(10)

        probe_agent_messages = probe_agent.get_messages()

        assert len(probe_agent_messages) == 4

        # Assert User Proxy Agent forwards the message to the Echo Agent
        forwarded_message = [message for message in probe_agent_messages if message.topics == "echo_topic"][0]
        assert forwarded_message.topics == "echo_topic"
        assert forwarded_message.payload["message"] == "Hello, world! @EchoAgent"
        assert forwarded_message.sender.id == UserProxyAgent.get_user_agent_id("test_user")
        assert forwarded_message.routing_slip is not None
        assert forwarded_message.routing_slip.get_steps_count() == 1
        assert forwarded_message.forward_header is None
        assert forwarded_message.recipient_list == [AgentTag(id="echo001", name="EchoAgent")]

        # Assert Echo Agent responds to the User Proxy Agent
        echo_response = [
            message
            for message in probe_agent_messages
            if message.topics == UserProxyAgent.get_user_outbox_topic("test_user")
        ][0]
        assert echo_response.topics == UserProxyAgent.get_user_outbox_topic("test_user")
        assert echo_response.payload["message"] == "Hello, world! @EchoAgent"
        assert echo_response.sender.name == "EchoAgent"
        assert echo_response.in_response_to == forwarded_message.id

        # Assert User Proxy Agent forwards the response to the User
        user_notifications = [message for message in probe_agent_messages if message.topics == user_message_topic]

        assert len(user_notifications) == 2

        user_response = [message for message in user_notifications if message.forward_header][0]

        assert user_response.topics == user_message_topic
        assert user_response.payload["message"] == "Hello, world! @EchoAgent"
        assert user_response.sender.id == UserProxyAgent.get_user_agent_id("test_user")
        assert user_response.forward_header
        assert user_response.forward_header.origin_message_id == echo_response.id
        assert user_response.forward_header.on_behalf_of.name == "EchoAgent"

        probe_agent.clear_messages()

        # Test that the UserProxyAgent will forward user messages to the user
        probe_agent.publish_dict(
            topic="default_topic",
            payload={"message": "Message for user [test_user]"},
            recipient_list=[AgentTag(id=UserProxyAgent.get_user_agent_id("test_user"), name="test_user")],
        )

        time.sleep(0.01)

        probe_agent_messages = probe_agent.get_messages()

        assert len(probe_agent_messages) == 1

        user_message = probe_agent_messages[0]

        assert user_message.topics == user_message_topic
        assert user_message.payload["message"] == "Message for user [test_user]"
        assert user_message.sender.id == UserProxyAgent.get_user_agent_id("test_user")
        assert user_message.forward_header
        assert user_message.forward_header.on_behalf_of.name == "ProbeAgent"

        probe_agent.clear_messages()

        # Send another User Agent Creation Request and make sure a duplicate agent is not created
        probe_agent.publish_dict(
            topic=GuildTopics.SYSTEM_TOPIC,
            payload=UserAgentCreationRequest(user_id="test_user", user_name="test_user").model_dump(),
            format=UserAgentCreationRequest,
        )

        time.sleep(0.01)

        probe_agent_messages = probe_agent.get_messages()

        assert len(probe_agent_messages) == 1

        assert probe_agent_messages[0].format == get_qualified_class_name(ConflictResponse)

        probe_agent.clear_messages()

        # Ensure only the User Proxy Agent and the Echo Agent are running
        probe_agent.publish_dict(
            topic=GuildTopics.SYSTEM_TOPIC,
            payload=RunningAgentListRequest(guild_id=guild.id).model_dump(),
            format=RunningAgentListRequest,
        )

        time.sleep(0.01)

        probe_agent_messages = probe_agent.get_messages()

        assert len(probe_agent_messages) == 1

        running_agents_response = probe_agent_messages[0].payload

        assert len(running_agents_response["agents"]) == 4

        agent_names = [agent["name"] for agent in running_agents_response["agents"]]
        agent_names.sort()

        assert sorted(agent_names) == sorted(
            [
                "EchoAgent",
                "ProbeAgent",
                manager_name,
                "test_user",
            ]
        )

        probe_agent.clear_messages()

    def test_message_broadcast(
        self, guild_id, guild_name, guild_description, messaging: MessagingConfig, database, org_id
    ):
        builder = GuildBuilder(guild_id, guild_name, guild_description).set_messaging(
            messaging.backend_module,
            messaging.backend_class,
            messaging.backend_config,
        )

        guild = builder.bootstrap(database, org_id)

        time.sleep(0.5)

        user_broadcast_topic = UserProxyAgent.BROADCAST_TOPIC

        user1 = "user01"
        user1_topic = UserProxyAgent.get_user_inbox_topic(user1)
        user1_message_topic = UserProxyAgent.get_user_notifications_topic(user1)
        user1_outbox_topic = UserProxyAgent.get_user_outbox_topic(user1)
        user1_message_forward_topic = f"user_message_forward:{user1}"

        user2 = "user02"
        user2_topic = UserProxyAgent.get_user_inbox_topic(user2)
        user2_message_topic = UserProxyAgent.get_user_notifications_topic(user2)
        user2_outbox_topic = UserProxyAgent.get_user_outbox_topic(user2)

        user3 = "test_user_3"
        user3_topic = UserProxyAgent.get_user_inbox_topic(user3)
        user3_message_topic = UserProxyAgent.get_user_notifications_topic(user3)
        user3_outbox_topic = UserProxyAgent.get_user_outbox_topic(user3)

        probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id("probe_agent")
            .set_name("ProbeAgent")
            .set_description("A probe agent")
            .add_additional_topic(GuildTopics.SYSTEM_TOPIC)
            .add_additional_topic(user1_message_forward_topic)
            .add_additional_topic(user1_topic)
            .add_additional_topic(user1_message_topic)
            .add_additional_topic(user1_outbox_topic)
            .add_additional_topic(user2_topic)
            .add_additional_topic(user2_message_topic)
            .add_additional_topic(user2_outbox_topic)
            .add_additional_topic(user3_topic)
            .add_additional_topic(user3_message_topic)
            .add_additional_topic(user3_outbox_topic)
            .add_additional_topic("default_topic")
            .build_spec()
        )

        probe_agent: ProbeAgent = guild._add_local_agent(probe_spec)  # type: ignore

        probe_agent.publish_dict(
            topic=GuildTopics.SYSTEM_TOPIC,
            payload=UserAgentCreationRequest(user_id=user1, user_name=user1).model_dump(),
            format=UserAgentCreationRequest,
        )

        time.sleep(0.5)

        probe_agent.publish_dict(
            topic=GuildTopics.SYSTEM_TOPIC,
            payload=UserAgentCreationRequest(user_id=user2, user_name=user2).model_dump(),
            format=UserAgentCreationRequest,
        )

        time.sleep(0.5)

        probe_agent.publish_dict(
            topic=GuildTopics.SYSTEM_TOPIC,
            payload=UserAgentCreationRequest(user_id=user3, user_name=user3).model_dump(),
            format=UserAgentCreationRequest,
        )

        time.sleep(0.5)

        probe_agent_messages = probe_agent.get_messages()

        assert len(probe_agent_messages) == 3

        user_agent_creation_response = UserAgentCreationResponse.model_validate(probe_agent_messages[0].payload)

        for message in probe_agent_messages:
            user_agent_creation_response = UserAgentCreationResponse.model_validate(message.payload)
            assert user_agent_creation_response.status_code == 201

        probe_agent.clear_messages()

        # Test that all agents get an forward the message on broadcast topic

        msg_id = probe_agent.publish_dict(
            topic=user_broadcast_topic,
            payload={"message": "Broadcast message"},
            format=MessageConstants.RAW_JSON_FORMAT,
        )

        msg_id_int = msg_id.to_int()

        time.sleep(1.0)  # Increased sleep time for EmbeddedMessagingBackend

        probe_agent_messages = probe_agent.get_messages()

        assert len(probe_agent_messages) == 3

        for message in probe_agent_messages:
            assert message.payload["message"] == "Broadcast message"
            assert message.topics is not None
            assert isinstance(message.topics, str)
            topic_type, user_id = message.topics.split(":")
            assert topic_type == "user_notifications"
            assert UserProxyAgent.get_user_agent_id(user_id) == message.sender.id
            assert message.forward_header is not None
            assert message.forward_header.origin_message_id == msg_id_int
            assert message.forward_header.on_behalf_of.name == "ProbeAgent"

        probe_agent.clear_messages()

        # Test that incoming messages are forwarded to the broadcast topic

        gemgen = GemstoneGenerator(100)

        send_id = gemgen.get_id(Priority.NORMAL)

        wrapped_message = Message(
            id_obj=send_id,
            topics="default_topic",
            sender=AgentTag(id="dummyUserId", name="dummy_user"),
            payload={"message": "Hello, world!"},
        )

        probe_agent.publish_dict(
            topic=user1_topic,
            payload=wrapped_message.model_dump(),
            format=Message,
            msg_id=send_id,
        )

        time.sleep(1.0)  # Increased sleep time for EmbeddedMessagingBackend

        probe_agent_messages = probe_agent.get_messages()

        assert len(probe_agent_messages) == 4

        default_topic_messages = [message for message in probe_agent_messages if message.topics == "default_topic"]

        assert len(default_topic_messages) == 1

        default_topic_message = default_topic_messages[0]

        assert default_topic_message.payload["message"] == "Hello, world!"
        assert default_topic_message.sender.id == UserProxyAgent.get_user_agent_id(user1)

        user_notifications = [
            message
            for message in probe_agent_messages
            if message.topics is not None
            and isinstance(message.topics, str)
            and message.topics.startswith("user_notifications")
        ]

        assert len(user_notifications) == 3

        notified_users = []
        for message in user_notifications:
            assert message.payload["message"] == "Hello, world!"
            assert message.topics is not None
            assert isinstance(message.topics, str)
            _, user_id = message.topics.split(":")
            assert message.sender.id == UserProxyAgent.get_user_agent_id(user_id)
            if message.forward_header:
                assert message.forward_header.origin_message_id == send_id.to_int()
                assert message.forward_header.on_behalf_of.name == "ProbeAgent"
                notified_users.append(user_id)

        assert user1 not in notified_users
