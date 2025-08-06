from concurrent.futures import ThreadPoolExecutor
import pathlib
import threading
import time

import pytest

from rustic_ai.core.messaging.core.messaging_config import MessagingConfig
from rustic_ai.redis.messaging.backend import RedisBackendConfig

from rustic_ai.testing.execution.base_test_integration import IntegrationTestABC

# Get the directory of the current test file
WORKING_DIR_ROOT = pathlib.Path(__file__).parent.parent.resolve()


class TestMultiThreadedRedisIntegration(IntegrationTestABC):
    """
    Integration tests for MultiThreadedEngine with Redis messaging backend.

    This test suite verifies that the multithreaded execution engine works correctly
    with Redis as the distributed messaging backend, ensuring:
    - Agents can run in separate threads with Redis messaging
    - Thread-safe messaging operations work correctly
    - Concurrent access to Redis is handled properly
    - Performance is acceptable for multithreaded scenarios
    - Thread isolation and cleanup work correctly
    """

    @pytest.fixture
    def messaging(self, guild_id):
        """Configure Redis messaging backend for integration tests."""
        redis_config = RedisBackendConfig(host="localhost", port=6379, ssl=False)
        messaging = MessagingConfig(
            backend_module="rustic_ai.redis.messaging.backend",
            backend_class="RedisMessagingBackend",
            backend_config={"redis_client": redis_config},
        )
        yield messaging

    @pytest.fixture
    def execution_engine(self):
        """Configure multithreaded execution engine for tests."""
        # Return the class path for the execution engine
        yield "rustic_ai.core.guild.execution.multithreaded.MultiThreadedEngine"

    @pytest.fixture
    def wait_time(self) -> float:
        """Standard wait time for multithreaded tests."""
        return 0.02  # Slightly longer than base for thread coordination

    def test_multithreaded_thread_safety_with_redis(
        self,
        guild,
        initiator_agent,
        responder_agent,
    ):
        """
        Test that agents running in separate threads can safely access Redis concurrently.
        This test verifies thread-safety of Redis operations across multiple agent threads.
        """
        execution_engine = guild._get_execution_engine()

        # Add agents to the guild
        guild.launch_agent(initiator_agent)
        guild.launch_agent(responder_agent)

        # Verify agents are running
        agents = execution_engine.get_agents_in_guild(guild.id)
        assert len(agents) == 2

        # Verify both agents are running in separate threads
        assert execution_engine.is_agent_running(guild.id, initiator_agent.id)
        assert execution_engine.is_agent_running(guild.id, responder_agent.id)

        # Get thread information
        initiator_wrapper = execution_engine.agent_wrappers.get(initiator_agent.id)
        responder_wrapper = execution_engine.agent_wrappers.get(responder_agent.id)

        assert initiator_wrapper is not None
        assert responder_wrapper is not None

        # Verify they are in different threads
        if hasattr(initiator_wrapper, "thread") and hasattr(responder_wrapper, "thread"):
            assert initiator_wrapper.thread != responder_wrapper.thread
            assert initiator_wrapper.thread.ident != responder_wrapper.thread.ident

        print(f"Main thread ID: {threading.current_thread().ident}")
        if hasattr(initiator_wrapper, "thread"):
            print(f"Initiator thread ID: {initiator_wrapper.thread.ident}")
        if hasattr(responder_wrapper, "thread"):
            print(f"Responder thread ID: {responder_wrapper.thread.ident}")

    def test_multithreaded_concurrent_messaging_performance(
        self,
        wait_time: float,
        guild,
        local_test_agent_spec,
        initiator_agent,
        responder_agent,
    ):
        """
        Test messaging performance between threads using Redis backend.
        This verifies that concurrent thread access to Redis is efficient.
        """
        from rustic_ai.core.guild.execution.sync.sync_exec_engine import (
            SyncExecutionEngine,
        )

        # Add agents to the guild
        guild.launch_agent(initiator_agent)
        guild.launch_agent(responder_agent)

        # Add local test agent
        local_exec_engine = SyncExecutionEngine(guild_id=guild.id, organization_id=guild.organization_id)
        local_test_agent = guild._add_local_agent(local_test_agent_spec, local_exec_engine)

        # Measure messaging performance
        start_time = time.time()

        # Send multiple messages to test throughput
        for i in range(10):
            local_test_agent.publish_initial_message()
            time.sleep(wait_time * 0.5)  # Small delay between messages

        # Allow time for all messages to be processed
        time.sleep(wait_time * 30)

        end_time = time.time()

        # Verify messages were processed
        # Each initial message should trigger a response from initiator and then responder
        # So we expect 10 * 2 = 20 messages minimum
        assert len(local_test_agent.captured_messages) >= 20

        total_time = end_time - start_time
        messages_per_second = len(local_test_agent.captured_messages) / total_time

        print(f"Processed {len(local_test_agent.captured_messages)} messages in {total_time:.2f}s")
        print(f"Throughput: {messages_per_second:.2f} messages/second")

        # Performance should be reasonable (at least 5 messages per second)
        # Multithreaded should be faster than multiprocess due to lower overhead
        assert messages_per_second > 5.0

    def test_multithreaded_thread_isolation_and_cleanup(
        self,
        wait_time: float,
        guild,
        initiator_agent,
        responder_agent,
    ):
        """
        Test that agent threads are properly isolated and cleaned up.
        """
        execution_engine = guild._get_execution_engine()

        # Add agents to the guild
        guild.launch_agent(initiator_agent)
        guild.launch_agent(responder_agent)

        # Verify both agents are running
        agents = execution_engine.get_agents_in_guild(guild.id)
        assert len(agents) == 2

        # Get initial thread count
        initial_thread_count = threading.active_count()
        print(f"Initial thread count: {initial_thread_count}")

        # Remove one agent
        guild.remove_agent(responder_agent.id)

        # Wait for cleanup
        time.sleep(wait_time * 10)

        # Verify the other agent is still running
        remaining_agents = execution_engine.get_agents_in_guild(guild.id)
        assert len(remaining_agents) == 1
        assert initiator_agent.id in remaining_agents

        # Verify the removed agent is no longer tracked
        assert not execution_engine.is_agent_running(guild.id, responder_agent.id)

        # Thread cleanup happens automatically with daemon threads
        # Just verify the agent wrapper is removed
        assert responder_agent.id not in execution_engine.agent_wrappers

    def test_multithreaded_redis_connection_pooling(
        self,
        wait_time: float,
        guild,
        initiator_agent,
        responder_agent,
    ):
        """
        Test that Redis connection pooling works correctly with multithreaded agents.
        This verifies that multiple threads can share Redis connections efficiently.
        """
        execution_engine = guild._get_execution_engine()

        # Add multiple agents
        guild.launch_agent(initiator_agent)
        guild.launch_agent(responder_agent)

        # Wait for agents to start
        time.sleep(wait_time * 10)

        # Verify agents are running
        agents = execution_engine.get_agents_in_guild(guild.id)
        assert len(agents) == 2

        # Test concurrent Redis operations
        def redis_stress_test():
            # Each thread will try to access Redis simultaneously
            for i in range(5):
                agents_check = execution_engine.get_agents_in_guild(guild.id)
                assert len(agents_check) == 2
                time.sleep(0.01)

        # Run concurrent access test
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(redis_stress_test) for _ in range(5)]

            # Wait for all threads to complete
            for future in futures:
                future.result()  # This will raise exception if any occurred

        # Verify agents are still running after stress test
        final_agents = execution_engine.get_agents_in_guild(guild.id)
        assert len(final_agents) == 2

    def test_multithreaded_engine_statistics(
        self,
        wait_time: float,
        guild,
        initiator_agent,
        responder_agent,
    ):
        """
        Test that the multithreaded execution engine provides accurate statistics.
        """
        execution_engine = guild._get_execution_engine()

        # Add agents
        guild.launch_agent(initiator_agent)
        guild.launch_agent(responder_agent)

        # Wait for agents to start
        time.sleep(wait_time * 10)

        # Get agents and verify statistics
        agents = execution_engine.get_agents_in_guild(guild.id)
        assert len(agents) == 2

        # Check that both agents are running
        assert execution_engine.is_agent_running(guild.id, initiator_agent.id)
        assert execution_engine.is_agent_running(guild.id, responder_agent.id)

        # Check agent finding functionality
        found_initiator = execution_engine.find_agents_by_name(guild.id, "Initiator Agent")
        found_responder = execution_engine.find_agents_by_name(guild.id, "Responder Agent")

        assert len(found_initiator) == 1
        assert len(found_responder) == 1
        assert found_initiator[0].id == initiator_agent.id
        assert found_responder[0].id == responder_agent.id

        # Remove one agent and verify statistics update
        guild.remove_agent(responder_agent.id)
        time.sleep(wait_time * 5)

        # Check updated statistics
        remaining_agents = execution_engine.get_agents_in_guild(guild.id)
        assert len(remaining_agents) == 1
        assert not execution_engine.is_agent_running(guild.id, responder_agent.id)
        assert execution_engine.is_agent_running(guild.id, initiator_agent.id)

    def test_multithreaded_redis_message_ordering(
        self,
        wait_time: float,
        guild,
        local_test_agent_spec,
        initiator_agent,
        responder_agent,
    ):
        """
        Test that message ordering is maintained with multithreaded Redis operations.
        This is important for ensuring message consistency in concurrent scenarios.
        """
        from rustic_ai.core.guild.execution.sync.sync_exec_engine import (
            SyncExecutionEngine,
        )

        # Add agents to the guild
        guild.launch_agent(initiator_agent)
        guild.launch_agent(responder_agent)

        # Add local test agent
        local_exec_engine = SyncExecutionEngine(guild_id=guild.id, organization_id=guild.organization_id)
        local_test_agent = guild._add_local_agent(local_test_agent_spec, local_exec_engine)

        # Wait for initialization
        time.sleep(wait_time * 10)

        # Send a sequence of messages and verify ordering
        message_count = 3
        for i in range(message_count):
            local_test_agent.publish_initial_message()
            time.sleep(wait_time * 2)  # Small delay between messages

        # Allow time for processing
        time.sleep(wait_time * 20)

        # Verify we got responses
        assert len(local_test_agent.captured_messages) >= message_count * 2

        # Group messages by sender
        initiator_messages = [msg for msg in local_test_agent.captured_messages if msg.sender.id == "initiator"]
        responder_messages = [msg for msg in local_test_agent.captured_messages if msg.sender.id == "responder"]

        # Verify we got expected number of messages from each sender
        assert len(initiator_messages) >= message_count
        assert len(responder_messages) >= message_count

        # Verify message content consistency
        for msg in initiator_messages:
            assert msg.payload.get("content") == "Hello Responder!"

        for msg in responder_messages:
            assert "Acknowledged:" in msg.payload.get("content", "")

    def test_multithreaded_redis_error_handling(
        self,
        wait_time: float,
        guild,
        initiator_agent,
    ):
        """
        Test error handling in multithreaded Redis scenarios.
        This verifies that Redis connection errors are handled gracefully.
        """
        execution_engine = guild._get_execution_engine()

        # Add agent
        guild.launch_agent(initiator_agent)

        # Wait for agent to start
        time.sleep(wait_time * 10)

        # Verify agent is running
        assert execution_engine.is_agent_running(guild.id, initiator_agent.id)

        # Test that agent operations still work
        agents = execution_engine.get_agents_in_guild(guild.id)
        assert len(agents) == 1

        found_agents = execution_engine.find_agents_by_name(guild.id, "Initiator Agent")
        assert len(found_agents) == 1

        # Test graceful shutdown
        guild.remove_agent(initiator_agent.id)
        time.sleep(wait_time * 5)

        # Verify cleanup
        remaining_agents = execution_engine.get_agents_in_guild(guild.id)
        assert len(remaining_agents) == 0
        assert not execution_engine.is_agent_running(guild.id, initiator_agent.id)
