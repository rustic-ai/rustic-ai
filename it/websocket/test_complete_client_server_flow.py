import asyncio
from datetime import datetime
import json
import logging
import sqlite3
import time

import httpx
import pytest
import redis
import websockets

from rustic_ai.core.guild.dsl import GuildTopics

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TestCompleteClientServerFlow:
    """
    Comprehensive integration test that simulates the complete client-server flow
    from guild creation through WebSocket communication, using Redis messaging
    backend and Ray execution engine.

    This test validates:
    - Guild creation and bootstrap process
    - Agent initialization and health monitoring
    - WebSocket connection establishment (system and user)
    - User agent creation flow
    - Real-time message routing and processing
    - System operations (stop guild)
    - Database state consistency
    - Redis message flow validation
    """

    @pytest.fixture(scope="function")
    async def infrastructure_clients(self):
        """Connect to existing infrastructure services"""
        # Redis client
        redis_client = redis.Redis(host="localhost", port=6379, decode_responses=True)

        # HTTP client for API calls
        http_client = httpx.AsyncClient(base_url="http://localhost:8880", timeout=30.0)

        # SQLite connection
        db_engine = sqlite3.connect("rustic_app.db")

        # Verify all services are accessible
        try:
            assert redis_client.ping() is True
            health_response = await http_client.get("/__health")
            assert health_response.status_code == 200
            assert db_engine.execute("SELECT 1").fetchone()[0] == 1
            logger.info("All infrastructure services are accessible")
        except Exception as e:
            logger.error(f"Infrastructure not ready: {e}")
            raise

        yield {"redis": redis_client, "http": http_client, "db": db_engine}

        # Cleanup
        await http_client.aclose()
        db_engine.close()

    @pytest.fixture
    async def redis_subscriber(self, infrastructure_clients):
        """Setup Redis subscriber for message monitoring"""
        redis_client = infrastructure_clients["redis"]
        subscriber = redis_client.pubsub()

        # Subscribe to all relevant topics before test starts using patterns
        # Topics are prefixed with guild ID, so we use patterns
        topic_patterns = [
            "*:heartbeat",
            "*:system_topic",
            "*:guild_status_topic",
            "*:echo_topic",
            "*:default_topic",
            f"*:{GuildTopics.AGENT_INBOX_PREFIX}:*",
            "*:user:testuser123:*",
        ]

        for pattern in topic_patterns:
            subscriber.psubscribe(pattern)

        yield subscriber

        # Cleanup
        subscriber.close()

    @pytest.fixture
    async def echo_blueprint(self, infrastructure_clients):
        """Create EchoAgent blueprint with Redis/Ray configuration"""
        http_client = infrastructure_clients["http"]

        # Step 1: Get the EchoAgent from the registry
        registry_response = await http_client.get("/api/registry/agents/")
        agents_data = registry_response.json()

        echo_agent_class = "rustic_ai.core.agents.testutils.echo_agent.EchoAgent"
        if echo_agent_class not in agents_data:
            raise Exception(f"EchoAgent not found in registry: {list(agents_data.keys())}")

        echo_agent_spec = agents_data[echo_agent_class]

        # Step 2: Register the EchoAgent in the catalog
        try:
            register_response = await http_client.post("/catalog/agents", json=echo_agent_spec)
            if register_response.status_code not in [201, 409]:  # 409 = already exists
                logger.error(f"Failed to register agent: {register_response.status_code} - {register_response.text}")
                raise Exception(f"Failed to register agent: {register_response.status_code}")
            logger.info(f"Agent registered successfully: {register_response.status_code}")
        except Exception as e:
            logger.info(f"Agent registration: {e}")
            # Agent might already be registered, continue

        # Step 3: Create a category for the blueprint (following data loading script pattern)
        category_payload = {"name": "Testing", "description": "Category for integration testing"}

        category_response = await http_client.post("/catalog/categories/", json=category_payload)
        if category_response.status_code == 201:
            category_id = category_response.json()["id"]
            logger.info(f"Created category with ID: {category_id}")
        elif category_response.status_code == 409:
            # Category might already exist, try to get existing categories
            categories_response = await http_client.get("/catalog/categories/")
            categories = categories_response.json()
            category_id = None
            for cat in categories:
                if cat["name"] == "Testing":
                    category_id = cat["id"]
                    break
            if not category_id:
                raise Exception("Failed to create or find Testing category")
            logger.info(f"Using existing category with ID: {category_id}")
        else:
            raise Exception(f"Failed to create category: {category_response.status_code} - {category_response.text}")

        # Step 4: Create blueprint with proper structure following the data loading script pattern
        blueprint_spec = {
            "name": "EchoTestBlueprint",
            "description": "Echo agent for integration testing",
            "version": "v1",
            "author_id": "test_author",
            "organization_id": "testorg456",
            "exposure": "private",
            "category_id": category_id,
            "spec": {
                "name": "EchoTestBlueprint",  # Match the blueprint name
                "description": "Echo agent for integration testing",  # Match the blueprint description
                "agents": [
                    {
                        "name": "EchoAgent",
                        "description": "Agent that echoes messages",
                        "class_name": "rustic_ai.core.agents.testutils.echo_agent.EchoAgent",
                        "additional_topics": ["echo_topic"],
                        "listen_to_default_topic": False,
                    }
                ],
                "properties": {
                    "messaging": {
                        "backend_module": "rustic_ai.redis.messaging.backend",
                        "backend_class": "RedisMessagingBackend",
                        "backend_config": {"redis_client": {"host": "localhost", "port": 6379}},
                    },
                    "execution_engine": "rustic_ai.core.guild.execution.sync.sync_exec_engine.SyncExecutionEngine",
                },
            },
        }

        response = await http_client.post("/catalog/blueprints/", json=blueprint_spec)
        if response.status_code != 201:
            logger.error(f"Blueprint creation failed: {response.status_code}")
            logger.error(f"Response: {response.text}")
        assert response.status_code == 201

        blueprint_id = response.json()["id"]
        logger.info(f"Created blueprint: {blueprint_id}")

        yield blueprint_id

        # Cleanup blueprint if needed
        # Note: May want to keep for debugging or clean up depending on test strategy

    async def wait_for_health_report(self, websocket, min_agents=2, timeout=10):
        """Wait for AgentsHealthReport with minimum agent count"""
        logger.info(f"Waiting for health report with at least {min_agents} agents")
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                message_raw = await asyncio.wait_for(websocket.recv(), timeout=1)
                message = json.loads(message_raw)

                if (
                    message.get("format") == "rustic_ai.core.guild.agent_ext.mixins.health.AgentsHealthReport"
                    and len(message.get("payload", {}).get("agents", {})) >= min_agents
                ):
                    logger.info(f"Received health report with {len(message['payload']['agents'])} agents")
                    return message
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.warning(f"Error waiting for health report: {e}")
                continue

        logger.warning(f"Timeout waiting for health report with {min_agents} agents")
        return None

    async def wait_for_redis_message(self, subscriber, topic, message_format, timeout=5):
        """Wait for specific message format on Redis topic"""
        logger.info(f"Waiting for Redis message on topic '{topic}' with format '{message_format}'")
        start_time = time.time()

        while time.time() - start_time < timeout:
            message = subscriber.get_message(timeout=1)
            if message and message["type"] == "message" and message["channel"] == topic:
                try:
                    data = json.loads(message["data"])
                    if data.get("format") == message_format:
                        logger.info(f"Found expected message on topic '{topic}'")
                        return data
                except json.JSONDecodeError:
                    continue

        logger.warning(f"Timeout waiting for message on topic '{topic}' with format '{message_format}'")
        return None

    async def monitor_message_flow(self, subscriber, expected_topics, timeout=10):
        """Monitor message flow across multiple topics"""
        logger.info(f"Monitoring message flow across topics: {expected_topics}")
        messages = []
        start_time = time.time()

        while time.time() - start_time < timeout:
            message = subscriber.get_message(timeout=1)
            if message and message["type"] == "message":
                topic = message["channel"]
                if topic in expected_topics:
                    try:
                        data = json.loads(message["data"])
                        messages.append({"topic": topic, "data": data})
                        logger.info(f"Captured message on topic '{topic}'")
                    except json.JSONDecodeError:
                        continue

            # Check if we got messages from all expected topics
            received_topics = set(msg["topic"] for msg in messages)
            if received_topics.issuperset(set(expected_topics)):
                logger.info("Received messages from all expected topics")
                break

        logger.info(f"Captured {len(messages)} messages across {len(set(msg['topic'] for msg in messages))} topics")
        return messages

    async def monitor_redis_bootstrap_messages(self, subscriber, timeout=15):
        """Monitor Redis messages during agent bootstrap"""
        logger.info("Monitoring Redis messages during bootstrap")
        bootstrap_messages = []
        start_time = time.time()

        while time.time() - start_time < timeout:
            message = subscriber.get_message(timeout=1)
            if message and message["type"] == "pmessage":  # Pattern-based message
                try:
                    data = json.loads(message["data"])
                    # Extract topic from channel (remove guild ID prefix for easier matching)
                    channel = (
                        message["channel"].decode() if isinstance(message["channel"], bytes) else message["channel"]
                    )
                    topic = channel.split(":")[-1] if ":" in channel else channel
                    bootstrap_messages.append(
                        {"topic": topic, "channel": channel, "data": data, "timestamp": time.time()}
                    )
                except json.JSONDecodeError:
                    continue

        logger.info(f"Captured {len(bootstrap_messages)} bootstrap messages")
        for msg in bootstrap_messages:
            logger.info(f"Bootstrap message: topic={msg['topic']}, channel={msg['channel']}")

        # If no messages, let's check what's in Redis
        if len(bootstrap_messages) == 0:
            logger.info("No messages captured, checking Redis for any recent activity...")

        return bootstrap_messages

    @pytest.mark.xfail(strict=False, reason="Incomplete test")
    @pytest.mark.asyncio
    async def test_complete_flow(self, infrastructure_clients, redis_subscriber, echo_blueprint):
        """
        Main test that executes the complete client-server flow
        """
        http_client = infrastructure_clients["http"]
        db_engine = infrastructure_clients["db"]

        logger.info("=== Starting Complete Client-Server Flow Test ===")

        # Phase 1: Guild Creation & Bootstrap
        logger.info("Phase 1: Guild Creation & Bootstrap")

        # Step 1.1: Start Redis monitoring at the very beginning
        redis_client = infrastructure_clients["redis"]
        bootstrap_subscriber = redis_client.pubsub()
        bootstrap_subscriber.psubscribe(f"*::{GuildTopics.AGENT_INBOX_PREFIX}")
        bootstrap_subscriber.psubscribe("*:heartbeat")

        # Wait a moment for subscription to be established
        await asyncio.sleep(2)
        logger.info(f"Redis monitoring started, subscribed to {GuildTopics.AGENT_INBOX_PREFIX} and heartbeat topics")

        # Step 1.2: Start monitoring task BEFORE guild creation
        monitoring_task = asyncio.create_task(self.monitor_redis_bootstrap_messages(bootstrap_subscriber, timeout=15))

        # Small delay to ensure monitoring is active
        await asyncio.sleep(0.5)

        # Step 1.3: Create Guild via Blueprint API
        guild_request = {"guild_name": "EchoTestGuild", "user_id": "testuser123", "org_id": "testorg456"}

        response = await http_client.post(f"/catalog/blueprints/{echo_blueprint}/guilds", json=guild_request)

        if response.status_code != 201:
            logger.error(f"Guild creation failed: {response.status_code}")
            logger.error(f"Response: {response.text}")
        assert response.status_code == 201
        guild_id = response.json()["id"]
        assert guild_id
        logger.info(f"Created guild: {guild_id}")

        # Wait a bit for the guild to be saved to the database
        await asyncio.sleep(2)

        # Step 1.4: Validate Database - Initial Guild Creation
        cursor = db_engine.cursor()

        # Check guild entry
        guild_row = cursor.execute("SELECT * FROM guilds WHERE id = ?", (guild_id,)).fetchone()

        # Debug: Let's see what guilds exist in the database
        all_guilds = cursor.execute("SELECT id, name, status FROM guilds").fetchall()
        logger.info(f"All guilds in database: {all_guilds}")
        logger.info(f"Looking for guild ID: {guild_id}")

        assert guild_row is not None
        assert guild_row[1] == "EchoTestGuild"  # name column
        logger.info("Guild entry validated in database")

        # Check agent entries
        agent_rows = cursor.execute("SELECT * FROM agents WHERE guild_id = ?", (guild_id,)).fetchall()
        assert len(agent_rows) >= 2  # At least EchoAgent + GuildManagerAgent

        agent_classes = [row[3] for row in agent_rows]  # class_name column
        assert "rustic_ai.core.agents.testutils.echo_agent.EchoAgent" in agent_classes
        assert "rustic_ai.core.agents.system.guild_manager_agent.GuildManagerAgent" in agent_classes
        logger.info(f"Agent entries validated in database: {len(agent_rows)} agents")

        # Get the bootstrap messages from the monitoring task
        bootstrap_messages = await monitoring_task

        # Validate expected messages received
        # Look for agent startup messages and heartbeat messages
        # Note: agent_inbox messages have channels like "guild_id:agent_inbox:agent_id"
        agent_inbox_messages = [msg for msg in bootstrap_messages if {GuildTopics.AGENT_INBOX_PREFIX} in msg["channel"]]
        heartbeat_messages = [msg for msg in bootstrap_messages if msg["topic"] == "heartbeat"]

        logger.info(f"Found {len(agent_inbox_messages)} agent_inbox messages")
        logger.info(f"Found {len(heartbeat_messages)} heartbeat messages")

        # Debug: Print all captured messages
        for msg in bootstrap_messages:
            logger.info(f"Message: topic={msg['topic']}, channel={msg['channel']}")

        # We should have at least agent startup messages
        assert len(agent_inbox_messages) >= 2  # GuildManagerAgent + EchoAgent
        logger.info(f"Received {len(agent_inbox_messages)} agent startup messages")

        health_reports = [msg for msg in bootstrap_messages if msg["topic"] == "guild_status"]
        assert len(health_reports) >= 1  # At least one health report
        logger.info(f"Received {len(health_reports)} health reports")

        # Phase 2: System WebSocket First & Health Monitoring
        logger.info("Phase 2: System WebSocket & Health Monitoring")

        # Step 2.1: Establish System WebSocket Connection
        system_ws_url = f"ws://localhost:8880/ws/guilds/{guild_id}/syscomms/testuser123"

        async with websockets.connect(system_ws_url) as system_ws:
            logger.info("System WebSocket connected")
            # WebSocket connection established successfully

            # Step 2.2: Wait for First AgentsHealthReport
            health_report = await self.wait_for_health_report(system_ws, min_agents=2, timeout=10)

            assert health_report is not None
            assert health_report["payload"]["guild_health"] == "ok"

            agents = health_report["payload"]["agents"]
            assert len(agents) >= 2  # GuildManagerAgent + EchoAgent

            # Validate all agents are healthy
            for agent_id, health in agents.items():
                assert health["checkstatus"] == "ok"
                logger.info(f"Agent {agent_id} is healthy")

            # Step 2.3: Validate Database - Running State
            guild_status = cursor.execute("SELECT status FROM guilds WHERE id = ?", (guild_id,)).fetchone()[0]
            assert guild_status == "RUNNING"
            logger.info("Guild status is RUNNING in database")

            # Phase 3: User WebSocket & User Agent Creation
            logger.info("Phase 3: User WebSocket & User Agent Creation")

            # Step 3.1: Establish User WebSocket Connection
            user_ws_url = f"ws://localhost:8880/ws/guilds/{guild_id}/usercomms/testuser123/Test%20User"

            async with websockets.connect(user_ws_url) as user_ws:
                logger.info("User WebSocket connected")
                # WebSocket connection established successfully

                # Step 3.2: Monitor UserAgentCreationRequest via Redis
                user_creation_msg = await self.wait_for_redis_message(
                    redis_subscriber,
                    topic="system",
                    message_format="rustic_ai.core.agents.system.guild_manager_agent.UserAgentCreationRequest",
                    timeout=5,
                )

                assert user_creation_msg is not None
                assert user_creation_msg["payload"]["user_id"] == "testuser123"
                assert user_creation_msg["payload"]["user_name"] == "Test User"
                logger.info("UserAgentCreationRequest validated")

                # Step 3.3: Wait for Updated Health Report with UserProxyAgent
                updated_health_report = await self.wait_for_health_report(
                    system_ws, min_agents=3, timeout=10  # Manager + Echo + UserProxy
                )

                assert updated_health_report is not None
                assert updated_health_report["payload"]["guild_health"] == "ok"

                agents = updated_health_report["payload"]["agents"]
                assert len(agents) >= 3

                # Check UserProxyAgent is present
                user_proxy_agents = [agent_id for agent_id in agents.keys() if "user_proxy" in agent_id.lower()]
                assert len(user_proxy_agents) >= 1
                logger.info(f"UserProxyAgent created: {user_proxy_agents[0]}")

                # Validate UserProxyAgent in Database
                user_proxy_rows = cursor.execute(
                    "SELECT * FROM agents WHERE guild_id = ? AND class_name LIKE '%UserProxyAgent%'", (guild_id,)
                ).fetchall()
                assert len(user_proxy_rows) >= 1
                logger.info("UserProxyAgent validated in database")

                # Phase 4: Chat Flow with Full Message Validation
                logger.info("Phase 4: Chat Flow & Message Validation")

                # Step 4.1: Send Participants Request
                participants_request = {
                    "format": "participantsRequest",
                    "payload": {"guild_id": guild_id},
                    "sender": {"id": "testuser123"},
                    "timestamp": datetime.now().isoformat(),
                    "conversationId": "789",
                }
                await system_ws.send(json.dumps(participants_request))
                logger.info("Participants request sent")

                # Step 4.2: Send Chat Message
                chat_message = {
                    "id": "msg123",
                    "format": "text",
                    "payload": {"text": "Hello Echo!"},
                    "sender": {"id": "testuser123", "name": "Test User"},
                    "conversationId": "789",
                    "timestamp": datetime.now().isoformat(),
                }
                await user_ws.send(json.dumps(chat_message))
                logger.info("Chat message sent: 'Hello Echo!'")

                # Step 4.3: Monitor Complete Message Flow via Redis
                expected_flow_topics = ["user:testuser123:inbox", "echo_topic", "user:testuser123:notifications"]

                message_flow = await self.monitor_message_flow(
                    redis_subscriber, expected_topics=expected_flow_topics, timeout=10
                )

                # Validate message routing
                assert any(msg["topic"] == "user:testuser123:inbox" for msg in message_flow)
                assert any(msg["topic"] == "echo_topic" for msg in message_flow)
                assert any(msg["topic"] == "user:testuser123:notifications" for msg in message_flow)
                logger.info("Message flow validated through Redis topics")

                # Step 4.4: Validate Echo Response
                response_raw = await asyncio.wait_for(user_ws.recv(), timeout=5)
                response = json.loads(response_raw)

                assert response["format"] == "text"
                assert "Echo:" in response["payload"]["text"]
                assert response["payload"]["text"] == "Echo: Hello Echo!"
                assert "echo" in response["sender"]["id"].lower()
                logger.info(f"Echo response validated: {response['payload']['text']}")

                # Phase 5: System Operations & Cleanup
                logger.info("Phase 5: System Operations & Cleanup")

                # Step 5.1: Stop Guild
                stop_request = {
                    "format": "stopGuildRequest",
                    "payload": {"guild_id": guild_id},
                    "sender": {"id": "testuser123"},
                }
                await system_ws.send(json.dumps(stop_request))
                logger.info("Stop guild request sent")

                # Wait for connections to close gracefully
                await asyncio.sleep(2)

        # Step 5.2: Validate Final Database State
        final_status = cursor.execute("SELECT status FROM guilds WHERE id = ?", (guild_id,)).fetchone()[0]
        assert final_status == "STOPPED"
        logger.info("Guild status is STOPPED in database")

        # Verify all agent records are preserved
        final_agent_count = cursor.execute("SELECT COUNT(*) FROM agents WHERE guild_id = ?", (guild_id,)).fetchone()[0]
        assert final_agent_count >= 3  # All agents preserved
        logger.info(f"All {final_agent_count} agent records preserved in database")

        logger.info("=== Complete Client-Server Flow Test PASSED ===")

    @pytest.mark.xfail(strict=False, reason="Incomplete test")
    @pytest.mark.asyncio
    async def test_redis_topic_structure(self, infrastructure_clients, redis_subscriber):
        """
        Test to validate Redis topic structure and naming conventions
        """
        redis_client = infrastructure_clients["redis"]

        # Test Redis connectivity and basic operations
        assert redis_client.ping() is True

        # Test topic subscription
        test_topics = [
            "heartbeat",
            "system",
            "guild_status",
            "user:testuser123:inbox",
            "user:testuser123:notifications",
            "echo_topic",
        ]

        # Verify subscriber is working
        for topic in test_topics:
            # Publish test message
            redis_client.publish(topic, json.dumps({"test": "message"}))

        # Give time for messages to be received
        await asyncio.sleep(1)

        # Check messages were received
        received_messages = []
        for _ in range(10):  # Check up to 10 messages
            message = redis_subscriber.get_message(timeout=0.1)
            if message and message["type"] == "message":
                received_messages.append(message["channel"])

        # Should have received test messages
        assert len(received_messages) > 0
        logger.info(f"Redis topic structure test passed. Received messages on: {received_messages}")

    @pytest.mark.xfail(strict=False, reason="Incomplete test")
    @pytest.mark.asyncio
    async def test_database_schema_validation(self, infrastructure_clients):
        """
        Test to validate database schema and basic operations
        """
        db_engine = infrastructure_clients["db"]
        cursor = db_engine.cursor()

        # Test basic database operations
        test_result = cursor.execute("SELECT 1").fetchone()[0]
        assert test_result == 1

        # Validate guilds table structure
        guilds_schema = cursor.execute("PRAGMA table_info(guilds)").fetchall()
        guild_columns = [col[1] for col in guilds_schema]

        expected_guild_columns = ["id", "name", "description", "status"]
        for col in expected_guild_columns:
            assert col in guild_columns

        # Validate agents table structure
        agents_schema = cursor.execute("PRAGMA table_info(agents)").fetchall()
        agent_columns = [col[1] for col in agents_schema]

        expected_agent_columns = ["id", "name", "class_name", "guild_id"]
        for col in expected_agent_columns:
            assert col in agent_columns

        logger.info("Database schema validation passed")
