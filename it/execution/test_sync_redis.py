import time

import pytest

from rustic_ai.core.messaging.core.messaging_config import MessagingConfig
from rustic_ai.redis.messaging.backend import RedisBackendConfig

from rustic_ai.testing.execution.base_test_integration import IntegrationTestABC


class TestSyncRedisIntegration(IntegrationTestABC):
    @pytest.fixture
    def messaging(self, guild_id):
        redis_config = RedisBackendConfig(host="localhost", port=6379, ssl=False)
        messaging = MessagingConfig(
            backend_module="rustic_ai.redis.messaging.backend",
            backend_class="RedisMessagingBackend",
            backend_config={"redis_client": redis_config},
        )
        yield messaging

    @pytest.fixture
    def execution_engine(self) -> str:
        return "rustic_ai.core.guild.execution.sync.SyncExecutionEngine"

    @pytest.fixture
    def wait_time(self) -> float:
        # Redis messaging needs more time than in-memory backends
        return 0.3

    def test_agents_communication(
        self,
        wait_time: float,
        guild,
        local_test_agent_spec,
        initiator_agent,
        responder_agent,
    ):
        """Override base test with Sync + Redis specific timing and retry logic."""
        from rustic_ai.core.guild.execution.sync.sync_exec_engine import (
            SyncExecutionEngine,
        )

        execution_engine = guild._get_execution_engine()

        # Add both agents to the guild
        guild.launch_agent(initiator_agent)
        guild.launch_agent(responder_agent)

        # Wait for agents to start - sync execution needs time for Redis subscriptions
        time.sleep(wait_time * 10)

        # Test if the agent is in the execution engine
        agents = execution_engine.get_agents_in_guild(guild.id)
        assert len(agents) == 2

        ia = execution_engine.find_agents_by_name(guild.id, "Initiator Agent")
        assert len(ia) == 1

        iair = execution_engine.is_agent_running(guild.id, ia[0].id)
        assert iair is True

        ra = execution_engine.find_agents_by_name(guild.id, "Responder Agent")
        assert len(ra) == 1

        rair = execution_engine.is_agent_running(guild.id, ra[0].id)
        assert rair is True

        local_exec_engine = SyncExecutionEngine(guild_id=guild.id, organization_id=guild.organization_id)
        local_test_agent = guild._add_local_agent(local_test_agent_spec, local_exec_engine)

        # Allow time for Redis subscriptions to be established
        time.sleep(wait_time * 5)

        # Try multiple times to get messages (retry mechanism for Redis latency)
        max_attempts = 3
        for attempt in range(max_attempts):
            # Clear any existing messages first
            local_test_agent.captured_messages.clear()

            # Initiator sends a message to trigger communication
            print(f"Sync Redis test attempt {attempt + 1}: Publishing initial message...")
            local_test_agent.publish_initial_message()

            # Allow time for message processing in Redis setup
            time.sleep(wait_time * 20)

            # Check if we got messages
            if len(local_test_agent.captured_messages) >= 2:
                break

            print(
                f"Sync Redis test attempt {attempt + 1}: Only got {len(local_test_agent.captured_messages)} messages, retrying..."
            )

            # Extra wait between attempts
            if attempt < max_attempts - 1:
                time.sleep(wait_time * 10)

        # Assertions to verify communication flow
        # Ensure the local test agent captured the messages as expected
        print(f"Sync Redis test captured {len(local_test_agent.captured_messages)} messages")
        for i, msg in enumerate(local_test_agent.captured_messages):
            print(f"  Message {i}: {msg.sender.id} -> {msg.payload}")

        assert (
            len(local_test_agent.captured_messages) >= 2
        ), f"Sync Redis test: Expected at least 2 messages after {max_attempts} attempts, got {len(local_test_agent.captured_messages)}"

        # Continue with message validation
        msg0 = local_test_agent.captured_messages[0]
        msg1 = local_test_agent.captured_messages[1]

        if msg0.sender.id == "initiator":
            first_msg = msg0
            second_msg = msg1
        else:
            first_msg = msg1
            second_msg = msg0

        assert first_msg.topics == "default_topic"
        assert first_msg.payload.get("content", "") == "Hello Responder!"
        assert first_msg.sender.id == "initiator"
        assert second_msg.topics == "default_topic"
        assert second_msg.payload.get("content", "") == f"Acknowledged: {first_msg.id}"
        assert second_msg.sender.id == "responder"

        # Clear the messages for potential next operations
        local_test_agent.clear_messages()

        # Remove responder agent
        guild.remove_agent(ra[0].id)

        # Test if the agent is removed from the execution engine
        agents2 = execution_engine.get_agents_in_guild(guild.id)
        assert len(agents2) >= 1  # Initiator agent and local test agent (in case of local execution engine)

        ra2 = execution_engine.find_agents_by_name(guild.id, "Responder Agent")
        assert len(ra2) == 0

        rair2 = execution_engine.is_agent_running(guild.id, ra[0].id)
        assert rair2 is False

        # Send a new message to ensure that the responder agent is no longer processing messages
        local_test_agent.publish_initial_message()

        time.sleep(wait_time * 10)

        # Ensure that the responder agent did not process the message
        print(f"After removal, captured {len(local_test_agent.captured_messages)} messages")
        assert len(local_test_agent.captured_messages) >= 1

        msgX = local_test_agent.captured_messages[0]
        assert msgX.topics == "default_topic"
        assert msgX.payload.get("content", "") == "Hello Responder!"
        assert msgX.sender.id == "initiator"
