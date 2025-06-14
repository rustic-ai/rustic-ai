#!/usr/bin/env python3
"""
Example: Distributed Agents with Shared Memory Messaging

This example demonstrates how to use the SharedMemoryMessagingBackend
to test distributed agents across different execution engines without
requiring Redis or other external dependencies.

The example shows:
1. Setting up a shared memory server
2. Creating agents with different execution engines
3. Testing message passing between distributed agents
4. Using Redis-like features for coordination
"""

import asyncio
import time

from rustic_ai.core.guild.agent import Agent
from rustic_ai.core.guild.execution.multithreaded.multithreaded_exec_engine import (
    MultiThreadedEngine,
)
from rustic_ai.core.guild.execution.sync.sync_exec_engine import SyncExecutionEngine
from rustic_ai.core.guild.guild import Guild
from rustic_ai.core.messaging.backend.shared_memory_backend import (
    SharedMemoryMessagingBackend,
    create_shared_messaging_config,
    start_shared_memory_server,
)
from rustic_ai.core.messaging.core.message import AgentTag, Message
from rustic_ai.core.messaging.core.messaging_config import MessagingConfig
from rustic_ai.core.utils.gemstone_id import GemstoneGenerator


class CoordinatorAgent(Agent):
    """Agent that coordinates work between other agents."""

    def __init__(self, agent_id: str, messaging_backend: SharedMemoryMessagingBackend):
        super().__init__(agent_id, agent_id)
        self.messaging_backend = messaging_backend
        self.tasks_assigned = 0
        self.results_received = 0

    async def handle_message(self, message: Message) -> None:
        """Handle incoming messages."""
        if message.payload.get("type") == "work_result":
            self.results_received += 1
            worker_id = message.payload.get("worker_id")
            result = message.payload.get("result")

            print(f"Coordinator received result from {worker_id}: {result}")

            # Store result in shared memory for other agents
            self.messaging_backend.hset(
                "results",
                f"task_{message.payload.get('task_id')}",
                str(result)
            )

            # Update completion status
            self.messaging_backend.set(
                f"task_status_{message.payload.get('task_id')}",
                "completed"
            )

    def assign_task(self, task_id: int, task_data: str, worker_topic: str) -> None:
        """Assign a task to a worker."""
        generator = GemstoneGenerator(1)

        task_message = Message(
            id_obj=generator.get_id(),
            sender=AgentTag(id=self.id, name=self.name),
            topics=worker_topic,
            payload={
                "type": "work_task",
                "task_id": task_id,
                "data": task_data,
                "coordinator_id": self.id
            }
        )

        self.messaging_backend.store_message("distributed_example", worker_topic, task_message)
        self.tasks_assigned += 1

        # Track task in shared memory
        self.messaging_backend.set(f"task_status_{task_id}", "assigned")

        print(f"Coordinator assigned task {task_id} to {worker_topic}")


class WorkerAgent(Agent):
    """Agent that processes work tasks."""

    def __init__(self, agent_id: str, messaging_backend: SharedMemoryMessagingBackend):
        super().__init__(agent_id, agent_id)
        self.messaging_backend = messaging_backend
        self.tasks_processed = 0

    async def handle_message(self, message: Message) -> None:
        """Handle incoming messages."""
        if message.payload.get("type") == "work_task":
            task_id = message.payload.get("task_id")
            task_data = message.payload.get("data")

            print(f"Worker {self.id} processing task {task_id}: {task_data}")

            # Simulate work
            await asyncio.sleep(0.5)
            result = "processed_" + task_data + "_by_" + self.id

            # Send result back to coordinator
            generator = GemstoneGenerator(1)
            result_message = Message(
                id_obj=generator.get_id(),
                sender=AgentTag(id=self.id, name=self.name),
                topics="coordinator_results",
                payload={
                    "type": "work_result",
                    "task_id": task_id,
                    "worker_id": self.id,
                    "result": result
                }
            )

            self.messaging_backend.store_message("distributed_example", "coordinator_results", result_message)
            self.tasks_processed += 1

            # Update worker status
            self.messaging_backend.sadd("active_workers", self.id)


class MonitorAgent(Agent):
    """Agent that monitors system status."""

    def __init__(self, agent_id: str, messaging_backend: SharedMemoryMessagingBackend):
        super().__init__(agent_id, agent_id)
        self.messaging_backend = messaging_backend
        self.monitoring = True

    async def handle_message(self, message: Message) -> None:
        """Handle monitoring commands."""
        if message.payload.get("type") == "status_request":
            await self.report_status()

    async def report_status(self) -> None:
        """Report system status."""
        # Get active workers
        active_workers = self.messaging_backend.smembers("active_workers")

        # Get completed tasks
        completed_tasks = []
        for i in range(10):  # Check first 10 tasks
            status = self.messaging_backend.get(f"task_status_{i}")
            if status == "completed":
                completed_tasks.append(i)

        print("Monitor Report:")
        print(f"  Active Workers: {len(active_workers)} - {list(active_workers)}")
        print(f"  Completed Tasks: {len(completed_tasks)} - {completed_tasks}")

    async def start_monitoring(self) -> None:
        """Start periodic monitoring."""
        while self.monitoring:
            await self.report_status()
            await asyncio.sleep(2)


def create_guild_with_shared_memory(execution_engine_type: str,
                                    messaging_backend: SharedMemoryMessagingBackend) -> Guild:
    """Create a guild with the specified execution engine and shared memory messaging."""

    # Create messaging config
    config_dict = create_shared_messaging_config(messaging_backend.server_url)
    config_dict["backend_config"]["auto_start_server"] = False
    messaging_config = MessagingConfig(**config_dict)

    # Create execution engine
    if execution_engine_type == "sync":
        exec_engine = SyncExecutionEngine()
    elif execution_engine_type == "multithreaded":
        exec_engine = MultiThreadedEngine(max_workers=4)
    else:
        raise ValueError(f"Unknown execution engine type: {execution_engine_type}")

    # Create guild
    guild = Guild(
        guild_id="distributed_test_guild",
        execution_engine=exec_engine,
        messaging_config=messaging_config
    )

    return guild


async def run_distributed_example():
    """Run the distributed agents example."""
    print("Starting Distributed Agents Example with Shared Memory Messaging")
    print("=" * 60)

    # Start shared memory server
    server, server_url = start_shared_memory_server()
    print(f"Started shared memory server at: {server_url}")

    try:
        # Create shared messaging backend for direct operations
        shared_backend = SharedMemoryMessagingBackend(server_url, auto_start_server=False)

        # Create coordinator agent with sync execution
        print("\nCreating Coordinator Guild (Sync Execution)...")
        coordinator_guild = create_guild_with_shared_memory("sync", shared_backend)
        coordinator = CoordinatorAgent("coordinator_1", shared_backend)
        coordinator_guild.add_agent(coordinator)

        # Subscribe coordinator to results
        coordinator_guild.messaging_interface.subscribe("coordinator_results", coordinator.handle_message)

        # Create worker agents with multithreaded execution
        print("Creating Worker Guilds (Multithreaded Execution)...")
        worker_guilds = []
        workers = []

        for i in range(3):
            worker_guild = create_guild_with_shared_memory("multithreaded", shared_backend)
            worker = WorkerAgent(f"worker_{i + 1}", shared_backend)
            worker_guild.add_agent(worker)

            # Subscribe worker to its topic
            worker_guild.messaging_interface.subscribe(f"worker_{i + 1}_tasks", worker.handle_message)

            worker_guilds.append(worker_guild)
            workers.append(worker)

        # Create monitor agent
        print("Creating Monitor Guild (Sync Execution)...")
        monitor_guild = create_guild_with_shared_memory("sync", shared_backend)
        monitor = MonitorAgent("monitor_1", shared_backend)
        monitor_guild.add_agent(monitor)

        # Start all guilds
        print("\nStarting all guilds...")
        coordinator_guild.start()
        for guild in worker_guilds:
            guild.start()
        monitor_guild.start()

        # Start monitoring in background
        monitor_task = asyncio.create_task(monitor.start_monitoring())

        # Wait for systems to initialize
        await asyncio.sleep(1)

        print("\nAssigning tasks to workers...")
        # Assign tasks to workers
        tasks = [
            (1, "analyze_data_set_A", "worker_1_tasks"),
            (2, "process_images_batch_1", "worker_2_tasks"),
            (3, "calculate_statistics", "worker_3_tasks"),
            (4, "generate_report", "worker_1_tasks"),
            (5, "validate_results", "worker_2_tasks"),
        ]

        for task_id, task_data, worker_topic in tasks:
            coordinator.assign_task(task_id, task_data, worker_topic)
            await asyncio.sleep(0.2)  # Small delay between assignments

        # Wait for tasks to complete
        print("\nWaiting for tasks to complete...")
        await asyncio.sleep(5)

        # Final status report
        print("\nFinal Status Report:")
        await monitor.report_status()

        # Show Redis-like data structures
        print("\nShared Memory Data Structures:")
        print(f"Active Workers: {shared_backend.smembers('active_workers')}")

        # Show task results
        print("\nTask Results:")
        for i in range(1, 6):
            result = shared_backend.hget("results", f"task_{i}")
            status = shared_backend.get(f"task_status_{i}")
            print(f"  Task {i}: {status} - {result}")

        # Test pattern subscription
        print("\nTesting pattern subscription...")
        pattern_messages = []

        def pattern_handler(message):
            pattern_messages.append(message)

        shared_backend.psubscribe("worker_*_tasks", pattern_handler)

        # Send a test message
        generator = GemstoneGenerator(1)
        test_msg = Message(
            id_obj=generator.get_id(),
            sender=AgentTag(id="test", name="Test"),
            topics="worker_test_tasks",
            payload={"type": "test", "data": "pattern_test"}
        )
        shared_backend.store_message("test", "worker_test_tasks", test_msg)

        await asyncio.sleep(0.5)
        print(f"Pattern subscription received {len(pattern_messages)} messages")

        # Stop monitoring
        monitor.monitoring = False
        monitor_task.cancel()

        # Stop all guilds
        print("\nStopping all guilds...")
        coordinator_guild.stop()
        for guild in worker_guilds:
            guild.stop()
        monitor_guild.stop()

        # Cleanup
        shared_backend.cleanup()

    finally:
        # Stop server
        server.cleanup()
        server.stop()
        print("\nShared memory server stopped")


def run_simple_messaging_test():
    """Run a simple test of the messaging backend."""
    print("Running Simple Messaging Test")
    print("=" * 30)

    # Start server
    server, url = start_shared_memory_server()
    print(f"Server started at: {url}")

    try:
        # Create two backends
        backend1 = SharedMemoryMessagingBackend(url, auto_start_server=False)
        backend2 = SharedMemoryMessagingBackend(url, auto_start_server=False)

        # Test basic messaging
        generator = GemstoneGenerator(1)

        # Backend1 sends message
        msg = Message(
            id_obj=generator.get_id(),
            sender=AgentTag(id="sender1", name="Sender 1"),
            topics="test_topic",
            payload={"message": "Hello from backend1!"}
        )
        backend1.store_message("test", "test_topic", msg)

        # Backend2 receives message
        messages = backend2.get_messages_for_topic("test_topic")
        print(f"Backend2 received {len(messages)} messages")
        if messages:
            print(f"Message content: {messages[0].payload}")

        # Test Redis-like operations
        backend1.set("shared_key", "shared_value")
        value = backend2.get("shared_key")
        print(f"Shared key-value: {value}")

        backend1.sadd("shared_set", "item1", "item2", "item3")
        members = backend2.smembers("shared_set")
        print(f"Shared set members: {members}")

        # Test subscription
        received_messages = []

        def handler(message):
            received_messages.append(message)
            print(f"Subscription received: {message.payload}")

        backend2.subscribe("notifications", handler)
        time.sleep(0.2)  # Let subscription register

        # Send notification
        notification = Message(
            id_obj=generator.get_id(),
            sender=AgentTag(id="notifier", name="Notifier"),
            topics="notifications",
            payload={"type": "alert", "message": "System status update"}
        )
        backend1.store_message("test", "notifications", notification)

        time.sleep(0.5)  # Wait for delivery
        print(f"Received {len(received_messages)} notifications via subscription")

        # Cleanup
        backend1.cleanup()
        backend2.cleanup()

    finally:
        server.stop()
        print("Test completed")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "simple":
        run_simple_messaging_test()
    else:
        asyncio.run(run_distributed_example())
