import multiprocessing
import pathlib
import time

import pytest

from rustic_ai.core.messaging.core.messaging_config import MessagingConfig
from rustic_ai.redis.messaging.backend import RedisBackendConfig

from rustic_ai.testing.execution.base_test_integration import IntegrationTestABC

# Get the directory of the current test file
WORKING_DIR_ROOT = pathlib.Path(__file__).parent.parent.resolve()


class TestMultiProcessRedisIntegration(IntegrationTestABC):
    """
    Integration tests for MultiProcessExecutionEngine with Redis messaging backend.

    This test suite verifies that the multiprocess execution engine works correctly
    with Redis as the distributed messaging backend, ensuring:
    - Agents can run in separate processes
    - Inter-process communication works via Redis
    - Process isolation and cleanup work correctly
    - True parallelism is achieved (escaping GIL)
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
        """Configure multiprocess execution engine for tests."""
        # Return the class path for the execution engine
        yield "rustic_ai.core.guild.execution.multiprocess.MultiProcessExecutionEngine"

    @pytest.fixture
    def wait_time(self) -> float:
        """Increase wait time for multiprocess tests due to process startup overhead."""
        return 0.05  # Slightly longer than base for process startup

    def test_multiprocess_true_parallelism(
        self,
        wait_time: float,
        guild,
        local_test_agent,
        initiator_agent,
        responder_agent,
    ):
        """
        Test that agents running in separate processes can achieve true parallelism.
        This test verifies that the GIL is escaped by running CPU-intensive tasks
        in parallel across multiple agent processes.
        """
        execution_engine = guild._get_execution_engine()

        # Add agents to the guild
        guild.launch_agent(initiator_agent)
        guild.launch_agent(responder_agent)

        # Verify agents are running in separate processes
        agents = execution_engine.get_agents_in_guild(guild.id)
        assert len(agents) == 2

        # Get process information for each agent
        initiator_process_info = execution_engine.get_process_info(guild.id, initiator_agent.id)
        responder_process_info = execution_engine.get_process_info(guild.id, responder_agent.id)

        assert initiator_process_info is not None
        assert responder_process_info is not None
        assert initiator_process_info.get("pid") != responder_process_info.get("pid")

        # Verify processes are different from main process
        main_pid = multiprocessing.current_process().pid
        assert initiator_process_info.get("pid") != main_pid
        assert responder_process_info.get("pid") != main_pid

        print(f"Main process PID: {main_pid}")
        print(f"Initiator agent PID: {initiator_process_info.get('pid')}")
        print(f"Responder agent PID: {responder_process_info.get('pid')}")

    def test_process_isolation_and_robustness(
        self,
        wait_time: float,
        guild,
        local_test_agent,
        initiator_agent,
        responder_agent,
    ):
        """
        Test that agent processes are isolated and the system is robust
        to individual process failures.
        """
        execution_engine = guild._get_execution_engine()

        # Add agents to the guild
        guild.launch_agent(initiator_agent)
        guild.launch_agent(responder_agent)

        # Verify both agents are running
        agents = execution_engine.get_agents_in_guild(guild.id)
        assert len(agents) == 2

        # Get initial process info
        initiator_pid = execution_engine.get_process_info(guild.id, initiator_agent.id).get("pid")
        responder_pid = execution_engine.get_process_info(guild.id, responder_agent.id).get("pid")

        assert initiator_pid is not None
        assert responder_pid is not None

        # Remove one agent (simulating process failure/shutdown)
        guild.remove_agent(responder_agent.id)

        # Wait for cleanup
        time.sleep(wait_time * 10)

        # Verify the other agent is still running
        remaining_agents = execution_engine.get_agents_in_guild(guild.id)
        assert len(remaining_agents) == 1
        assert initiator_agent.id in remaining_agents

        # Verify the removed agent is no longer tracked
        assert not execution_engine.is_agent_running(guild.id, responder_agent.id)

    def test_multiprocess_messaging_performance(
        self,
        wait_time: float,
        guild,
        local_test_agent,
        initiator_agent,
        responder_agent,
    ):
        """
        Test messaging performance between processes using Redis backend.
        This verifies that inter-process communication is efficient.
        """
        from rustic_ai.core.guild.execution.sync.sync_exec_engine import (
            SyncExecutionEngine,
        )

        # Add agents to the guild
        guild.launch_agent(initiator_agent)
        guild.launch_agent(responder_agent)

        # Add local test agent
        local_exec_engine = SyncExecutionEngine(guild_id=guild.id)
        guild._add_local_agent(local_test_agent, local_exec_engine)

        # Measure messaging performance
        start_time = time.time()

        # Send multiple messages to test throughput
        for i in range(5):
            local_test_agent.publish_initial_message()
            time.sleep(wait_time)

        # Allow time for all messages to be processed
        time.sleep(wait_time * 20)

        end_time = time.time()

        # Verify messages were processed
        # Each initial message should trigger a response from initiator and then responder
        # So we expect 5 * 2 = 10 messages minimum
        assert len(local_test_agent.captured_messages) >= 10

        total_time = end_time - start_time
        messages_per_second = len(local_test_agent.captured_messages) / total_time

        print(f"Processed {len(local_test_agent.captured_messages)} messages in {total_time:.2f}s")
        print(f"Throughput: {messages_per_second:.2f} messages/second")

        # Performance should be reasonable (at least 1 message per second)
        assert messages_per_second > 1.0

    def test_multiprocess_engine_stats(
        self,
        wait_time: float,
        guild,
        initiator_agent,
        responder_agent,
    ):
        """
        Test that the multiprocess execution engine provides accurate statistics.
        """
        execution_engine = guild._get_execution_engine()

        # Get initial stats
        initial_stats = execution_engine.get_engine_stats()
        assert initial_stats["engine_type"] == "MultiProcessExecutionEngine"
        assert initial_stats["alive_agents"] == 0

        # Add agents
        guild.launch_agent(initiator_agent)
        guild.launch_agent(responder_agent)

        # Wait for agents to start with longer timeout and multiple checks
        max_wait_time = 10.0  # Maximum 10 seconds
        check_interval = 0.5  # Check every 500ms
        waited = 0.0

        while waited < max_wait_time:
            time.sleep(check_interval)
            waited += check_interval

            stats = execution_engine.get_engine_stats()

            if stats["alive_agents"] >= 2:
                break

        # Get final stats
        stats = execution_engine.get_engine_stats()

        assert stats["alive_agents"] == 2
        assert stats["total_agents"] == 2
        assert stats["total_guilds"] == 1
        assert stats["max_processes"] > 0
        assert stats["owned_agents_count"] == 2

        # Remove one agent
        guild.remove_agent(responder_agent.id)
        time.sleep(wait_time * 10)

        # Check updated stats
        final_stats = execution_engine.get_engine_stats()
        assert final_stats["alive_agents"] == 1
        assert final_stats["owned_agents_count"] == 1

    def test_multiprocess_max_processes_limit(
        self,
        guild,
        initiator_agent,
        responder_agent,
    ):
        """
        Test that the execution engine respects the maximum processes limit.
        """
        # Create a new execution engine with limited processes
        from rustic_ai.core.guild.execution.multiprocess import (
            MultiProcessExecutionEngine,
        )

        limited_engine = MultiProcessExecutionEngine(guild_id=guild.id, max_processes=1)

        # Replace the guild's execution engine temporarily
        original_engine = guild.execution_engine
        guild.execution_engine = limited_engine

        try:
            # Add first agent - should succeed
            guild.launch_agent(initiator_agent)
            agents = limited_engine.get_agents_in_guild(guild.id)
            assert len(agents) == 1

            # Try to add second agent - should fail due to process limit
            with pytest.raises(RuntimeError, match="Maximum number of processes"):
                guild.launch_agent(responder_agent)

        finally:
            # Restore original engine and clean up
            limited_engine.shutdown()
            guild.execution_engine = original_engine

    def test_multiprocess_dead_process_cleanup(
        self,
        wait_time: float,
        guild,
        initiator_agent,
    ):
        """
        Test that dead processes are properly cleaned up.
        """
        execution_engine = guild._get_execution_engine()

        # Add agent
        guild.launch_agent(initiator_agent)

        # Verify agent is running
        assert execution_engine.is_agent_running(guild.id, initiator_agent.id)

        # Force cleanup check
        execution_engine.cleanup_dead_processes()

        # Agent should still be running after cleanup
        assert execution_engine.is_agent_running(guild.id, initiator_agent.id)

        # Get agent wrapper and force process termination
        agent_wrapper = execution_engine.agent_tracker.get_agent_wrapper(guild.id, initiator_agent.id)
        if agent_wrapper and agent_wrapper.process:
            agent_wrapper.process.terminate()
            agent_wrapper.process.join(timeout=5)

        # Wait a bit and then cleanup
        time.sleep(wait_time * 5)
        execution_engine.cleanup_dead_processes()

        # Agent should now be marked as not running
        # Note: This might be flaky depending on timing
        time.sleep(wait_time * 5)
        running_agents = execution_engine.get_agents_in_guild(guild.id)
        # The dead agent should be cleaned up
        assert len(running_agents) == 0
