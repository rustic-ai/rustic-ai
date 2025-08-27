import asyncio
import json
import os
import time

import httpx
import pytest
import websockets

from rustic_ai.api_server.guilds.schema import LaunchGuildReq
from rustic_ai.core.agents.testutils.echo_agent import EchoAgent
from rustic_ai.core.agents.utils.user_proxy_agent import UserProxyAgent
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.guild.dsl import AgentSpec, GuildSpec
from rustic_ai.core.guild.metastore import Metastore
from rustic_ai.core.messaging.client.message_tracking_store import (
    SqlMessageTrackingStore,
)
from rustic_ai.core.messaging.core.message import (
    AgentTag,
    Message,
    MessageConstants,
    RoutingDestination,
    RoutingRule,
    RoutingSlip,
)
from rustic_ai.core.messaging.core.messaging_config import MessagingConfig
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.core.utils.gemstone_id import GemstoneGenerator
from rustic_ai.core.utils.priority import Priority


class TestServer:
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

    @pytest.fixture(
        params=[
            pytest.param(
                MessagingConfig(
                    backend_module="rustic_ai.core.messaging.backend",
                    backend_class="InMemoryMessagingBackend",
                    backend_config={},
                ),
                id="InMemoryMessagingBackend",
            ),
            pytest.param(
                MessagingConfig(
                    backend_module="rustic_ai.redis.messaging.backend",
                    backend_class="RedisMessagingBackend",
                    backend_config={
                        "redis_client": {
                            "host": "localhost",
                            "port": 6379,
                            "pubsub_health_monitor_initial_delay": 0.1,  # Fast startup for integration tests
                        }
                    },
                ),
                id="RedisMessagingBackend",
            ),
            pytest.param(
                MessagingConfig(
                    backend_module="rustic_ai.core.messaging.backend.embedded_backend",
                    backend_class="EmbeddedMessagingBackend",
                    backend_config={"port": 31145, "auto_start_server": True},
                ),
                id="EmbeddedMessagingBackend",
                marks=pytest.mark.xfail(
                    reason="EmbeddedMessagingBackend is not fully reliable yet",
                ),
            ),
        ],
    )
    def guild(self, echo_agent, request) -> GuildSpec:
        messaging = request.param

        builder = GuildBuilder(guild_name="guild_name_123", guild_description="Websocket testing guild").add_agent_spec(
            echo_agent
        )

        builder.set_messaging(
            messaging.backend_module,
            messaging.backend_class,
            messaging.backend_config,
        )

        builder.set_property("client_type", "rustic_ai.core.messaging.client.exactly_once_client.ExactlyOnceClient")
        builder.set_property(
            "client_properties",
            {
                "tracking_store_class": get_qualified_class_name(SqlMessageTrackingStore),
                "tracking_store_props": {"db": os.environ.get("RUSTIC_METASTORE", Metastore.get_db_url())},
            },
        )

        return builder.build_spec()

    @pytest.fixture
    def generator(self):
        """
        Fixture that returns a GemstoneGenerator instance with a seed of 1.
        """
        return GemstoneGenerator(1)

    @pytest.mark.asyncio
    async def test_websocket_interaction(self, guild: GuildSpec, generator: GemstoneGenerator, org_id):
        server = "127.0.0.1:8880"
        # Increase wait time for shared memory operations
        wait_time = 0.5

        routing_slip = RoutingSlip(
            steps=[
                RoutingRule(
                    agent=AgentTag(name="EchoAgent"),
                    destination=RoutingDestination(
                        topics=UserProxyAgent.get_user_outbox_topic("user123"),
                    ),
                ),
                RoutingRule(
                    agent=AgentTag(id=UserProxyAgent.get_user_agent_id("user123")),
                    method_name="unwrap_and_forward_message",
                    destination=RoutingDestination(
                        topics="echo_topic",
                    ),
                ),
            ]
        )

        guild.routes = routing_slip

        async with httpx.AsyncClient(base_url=f"http://{server}", timeout=wait_time * 2) as client:
            req = LaunchGuildReq(spec=guild, org_id=org_id)
            req_data = json.loads(req.model_dump_json())
            new_guild_resp = await asyncio.wait_for(client.post("/api/guilds", json=req_data), wait_time * 2)

            assert new_guild_resp.status_code == 201
            # Extra wait for EmbeddedMessagingBackend to ensure agents are fully subscribed
            time.sleep(wait_time * 2)

            no_messages = await asyncio.wait_for(
                client.get(f"/api/guilds/{guild.id}/user123/messages", timeout=wait_time), wait_time
            )

            assert no_messages.status_code == 200
            no_messages_json = no_messages.json()
            assert len(no_messages_json) == 0

        # Additional wait for EmbeddedMessagingBackend agents to be fully ready
        time.sleep(wait_time * 2)

        async with websockets.connect(
            f"ws://{server}/ws/guilds/{guild.id}/usercomms/user123/user_name_123"
        ) as websocket:

            msg = Message(
                generator.get_id(Priority.NORMAL),
                topics="default_topic",
                sender={"id": "user123", "name": "user 123"},
                format=MessageConstants.RAW_JSON_FORMAT.value,
                payload={"content": "Hello, guild!"},
            )

            # Test sending a message with string id
            msg_dict = msg.model_dump()
            msg_dict["id"] = str(msg_dict["id"])

            await asyncio.sleep(wait_time)
            await asyncio.wait_for(websocket.send(json.dumps(msg_dict)), wait_time)
            await asyncio.sleep(wait_time * 2)

            wresp0 = []
            while True:
                try:
                    wr = await asyncio.wait_for(websocket.recv(), wait_time)
                    wresp0.append(wr)
                except TimeoutError:
                    break

            assert len(wresp0) == 2

            json0 = json.loads(wresp0[1])

            assert json0["payload"]["content"] == "Hello, guild!"
            assert json0["sender"]["id"] == UserProxyAgent.get_user_agent_id("user123")
            assert json0["sender"]["name"] == "user_name_123"
            assert json0["forward_header"]["on_behalf_of"]["name"] == "EchoAgent"

            # Test sending a message with int id
            msg = Message(
                generator.get_id(Priority.NORMAL),
                topics="default_topic",
                sender={"id": "user123", "name": "user 123"},
                format=MessageConstants.RAW_JSON_FORMAT.value,
                payload={"content": "Hello, guild INT!"},
            )

            msg_dict = msg.model_dump()

            await asyncio.wait_for(websocket.send(json.dumps(msg_dict)), wait_time)
            await asyncio.sleep(2)

            wrespi = []
            while True:
                try:
                    wr = await asyncio.wait_for(websocket.recv(), wait_time)
                    wrespi.append(wr)
                except TimeoutError:
                    break

            assert len(wrespi) == 2

            jsoni = json.loads(wrespi[1])

            assert jsoni["payload"]["content"] == "Hello, guild INT!"
            assert jsoni["sender"]["id"] == UserProxyAgent.get_user_agent_id("user123")
            assert jsoni["sender"]["name"] == "user_name_123"
            assert jsoni["forward_header"]["on_behalf_of"]["name"] == "EchoAgent"

            # Test sending a message without id
            msg = Message(
                generator.get_id(Priority.NORMAL),
                topics="default_topic",
                sender={"id": "user123", "name": "user 123"},
                format=MessageConstants.RAW_JSON_FORMAT.value,
                payload={"content": "Hello, guild NOID!"},
            )

            msg_dict = msg.model_dump()
            del msg_dict["id"]
            await asyncio.sleep(1)
            await asyncio.wait_for(websocket.send(json.dumps(msg_dict)), wait_time)
            await asyncio.sleep(2)

            wsrespx = []
            while True:
                try:
                    wr = await asyncio.wait_for(websocket.recv(), wait_time)
                    wsrespx.append(wr)
                except TimeoutError:
                    break

            assert len(wsrespx) == 2

            jsonx = json.loads(wsrespx[1])

            assert jsonx["payload"]["content"] == "Hello, guild NOID!"
            assert jsonx["sender"]["id"] == UserProxyAgent.get_user_agent_id("user123")
            assert jsonx["sender"]["name"] == "user_name_123"
            assert jsonx["forward_header"]["on_behalf_of"]["name"] == "EchoAgent"

            # Test sending an invalid message
            msg2 = Message(
                generator.get_id(Priority.NORMAL),
                topics="default_topic",
                sender={"id": "user123", "name": "user 123"},
                format=MessageConstants.RAW_JSON_FORMAT.value,
                payload={"content": "Hello, guild 2!"},
            )

            # We want to ensure that the server does not crash when receiving an invalid content
            await asyncio.wait_for(websocket.send("invalid json: something"), wait_time)
            await asyncio.sleep(2)
            await asyncio.wait_for(websocket.send(json.dumps(msg2.model_dump())), wait_time)
            await asyncio.sleep(2)

            wsresp1 = []
            while True:
                try:
                    wr = await asyncio.wait_for(websocket.recv(), wait_time)
                    wsresp1.append(wr)
                except TimeoutError:
                    break

            assert len(wsresp1) == 2

            json1 = json.loads(wsresp1[1])

            assert json1["payload"]["content"] == "Hello, guild 2!"
            assert json1["sender"]["id"] == UserProxyAgent.get_user_agent_id("user123")
            assert json1["sender"]["name"] == "user_name_123"
            assert json0["forward_header"]["on_behalf_of"]["name"] == "EchoAgent"

            # Test sending invalid JSON
            msg3 = Message(
                generator.get_id(Priority.NORMAL),
                topics="default_topic",
                sender={"id": "user123", "name": "user 123"},
                format=MessageConstants.RAW_JSON_FORMAT.value,
                payload={"content": "Hello, guild 3!"},
            )

            await asyncio.wait_for(websocket.send(json.dumps({"test": "invalid"})), wait_time)
            await asyncio.sleep(3)
            await asyncio.wait_for(websocket.send(json.dumps(msg3.model_dump())), wait_time)
            await asyncio.sleep(5)

            wsresp2 = []
            while True:
                try:
                    wr = await asyncio.wait_for(websocket.recv(), wait_time)
                    wsresp2.append(wr)
                except TimeoutError:
                    break

            assert len(wsresp2) == 2

            json2 = json.loads(wsresp2[1])

            assert json2["payload"]["content"] == "Hello, guild 3!"
            assert json2["sender"]["id"] == UserProxyAgent.get_user_agent_id("user123")
            assert json2["sender"]["name"] == "user_name_123"
            assert json0["forward_header"]["on_behalf_of"]["name"] == "EchoAgent"

        # Test fetching historical messages
        async with httpx.AsyncClient(base_url=f"http://{server}", timeout=wait_time * 2) as client:
            messages = await asyncio.wait_for(client.get(f"/api/guilds/{guild.id}/user123/messages"), wait_time * 2)

            assert messages.status_code == 200
            messages_json = messages.json()
            assert len(messages_json) == 10
            assert messages_json[1]["payload"]["content"] == "Hello, guild!"
            assert messages_json[1]["sender"]["id"] == UserProxyAgent.get_user_agent_id("user123")
            assert messages_json[1]["sender"]["name"] == "user_name_123"
            assert json0["forward_header"]["on_behalf_of"]["name"] == "EchoAgent"

            assert messages_json[3]["payload"]["content"] == "Hello, guild INT!"

            assert messages_json[5]["payload"]["content"] == "Hello, guild NOID!"

            assert messages_json[7]["payload"]["content"] == "Hello, guild 2!"

            assert messages_json[9]["payload"]["content"] == "Hello, guild 3!"
