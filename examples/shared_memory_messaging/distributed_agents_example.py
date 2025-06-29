#!/usr/bin/env python3
"""
Example: Distributed Agents with Embedded Messaging

This example demonstrates how to use the EmbeddedMessagingBackend
to test distributed agents across different execution engines without
requiring Redis or other external dependencies.

The example shows:
1. Setting up an embedded messaging server
2. Creating agents with different execution engines
3. Testing message passing between distributed agents
4. Using message-based coordination features
"""

import asyncio
import threading
import time
from typing import Any, Dict, Set

from rustic_ai.core.guild.agent import Agent
from rustic_ai.core.guild.execution.multithreaded.multithreaded_exec_engine import (
    MultiThreadedEngine,
)
from rustic_ai.core.guild.execution.sync.sync_exec_engine import SyncExecutionEngine
from rustic_ai.core.guild.guild import Guild
from rustic_ai.core.messaging.backend.embedded_backend import (
    EmbeddedMessagingBackend,
    EmbeddedServer,
    create_embedded_messaging_config,
)
from rustic_ai.core.messaging.core.message import AgentTag, Message
from rustic_ai.core.messaging.core.messaging_config import MessagingConfig
from rustic_ai.core.utils.gemstone_id import GemstoneGenerator


def start_server_thread(port=31143):
    """Start server in background thread for examples."""
    def run_server():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        server = EmbeddedServer(port=port)
        loop.run_until_complete(server.start())
        try:
            loop.run_forever()
        finally:
            loop.run_until_complete(server.stop())
            loop.close()

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    time.sleep(0.3)  # Wait for server to start
    return port


class CoordinatorAgent(Agent):
    """Agent that coordinates work between other agents."""

    def __init__(self, agent_id: str, messaging_backend: EmbeddedMessagingBackend):
        super().__init__(agent_id, agent_id)
        self.messaging_backend = messaging_backend
        self.tasks_assigned = 0
        self.results_received = 0
        self.task_results: Dict[str, Dict[str, Any]] = {}  # Store results in memory since we don't have Redis operations

    async def handle_message(self, message: Message) -> None:
        """Handle incoming messages."""
        if message.payload.get("type") == "work_result":
            self.results_received += 1
            worker_id = message.payload.get("worker_id")
            result = message.payload.get("result")
            task_id = message.payload.get("task_id")

            print(f"Coordinator received result from {worker_id}: {result}")

            # Store result in memory
            self.task_results[f"task_{task_id}"] = {
                "worker_id": worker_id,
                "result": result,
                "status": "completed"
            }

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

        print(f"Coordinator assigned task {task_id} to {worker_topic}")


class WorkerAgent(Agent):
    """Agent that processes work tasks."""

    def __init__(self, agent_id: str, messaging_backend: EmbeddedMessagingBackend):
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


class MonitorAgent(Agent):
    """Agent that monitors system status."""

    def __init__(self, agent_id: str, messaging_backend: EmbeddedMessagingBackend, coordinator: CoordinatorAgent):
        super().__init__(agent_id, agent_id)
        self.messaging_backend = messaging_backend
        self.coordinator = coordinator
        self.monitoring = True
        self.active_workers: Set[str] = set()

    async def handle_message(self, message: Message) -> None:
        """Handle monitoring commands."""
        if message.payload.get("type") == "status_request":
            await self.report_status()
        elif message.payload.get("type") == "work_result":
            # Track worker activity
            worker_id = message.payload.get("worker_id")
            if worker_id:
                self.active_workers.add(worker_id)

    async def report_status(self) -> None:
        """Report system status."""
        completed_tasks = [k for k, v in self.coordinator.task_results.items()
                           if v.get("status") == "completed"]

        print("Monitor Report:")
        print(f"  Active Workers: {len(self.active_workers)} - {list(self.active_workers)}")
        print(f"  Tasks Assigned: {self.coordinator.tasks_assigned}")
        print(f"  Results Received: {self.coordinator.results_received}")
        print(f"  Completed Tasks: {len(completed_tasks)} - {[t.replace('task_', '') for t in completed_tasks]}")

    async def start_monitoring(self) -> None:
        """Start periodic monitoring."""
        while self.monitoring:
            await self.report_status()
            await asyncio.sleep(2)


def create_guild_with_embedded_messaging(execution_engine_type: str, port: int) -> Guild:
    """Create a guild with the specified execution engine and embedded messaging."""

    # Create messaging config
    config_dict = create_embedded_messaging_config(port=port)
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
    print("Starting Distributed Agents Example with Embedded Messaging")
    print("=" * 70)

    # Start socket server
    port = start_server_thread(31143)
    print(f"Started socket server on port: {port}")

    try:
        # Create shared messaging backend for direct operations
        shared_backend = EmbeddedMessagingBackend(port=port, auto_start_server=False)

        # Create coordinator agent with sync execution
        print("\nCreating Coordinator Guild (Sync Execution)...")
        coordinator_guild = create_guild_with_embedded_messaging("sync", port)
        coordinator = CoordinatorAgent("coordinator_1", shared_backend)
        coordinator_guild.add_agent(coordinator)

        # Subscribe coordinator to results
        coordinator_guild.messaging_interface.subscribe("coordinator_results", coordinator.handle_message)

        # Create worker agents with multithreaded execution
        print("Creating Worker Guilds (Multithreaded Execution)...")
        worker_guilds = []
        workers = []

        for i in range(3):
            worker_guild = create_guild_with_embedded_messaging("multithreaded", port)
            worker = WorkerAgent(f"worker_{i + 1}", shared_backend)
            worker_guild.add_agent(worker)

            # Subscribe worker to its topic
            worker_guild.messaging_interface.subscribe(f"worker_{i + 1}_tasks", worker.handle_message)

            worker_guilds.append(worker_guild)
            workers.append(worker)

        # Create monitor agent
        print("Creating Monitor Guild (Sync Execution)...")
        monitor_guild = create_guild_with_embedded_messaging("sync", port)
        monitor = MonitorAgent("monitor_1", shared_backend, coordinator)
        monitor_guild.add_agent(monitor)

        # Subscribe monitor to results to track worker activity
        monitor_guild.messaging_interface.subscribe("coordinator_results", monitor.handle_message)

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

        # Show task results
        print("\nTask Results:")
        for task_key, result_info in coordinator.task_results.items():
            print(f"  {task_key}: {result_info['status']} by {result_info['worker_id']} - {result_info['result']}")

        # Test message history
        print("\nTesting message history...")
        all_results = shared_backend.get_messages_for_topic("coordinator_results")
        print(f"Total result messages: {len(all_results)}")

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

    except Exception as e:
        print(f"Error in distributed example: {e}")
        raise


def run_simple_messaging_test():
    """Run a simple test of the messaging backend."""
    print("Running Simple Messaging Test")
    print("=" * 30)

    # Start server
    port = start_server_thread(31144)
    print(f"Server started on port: {port}")

    try:
        # Create two backends
        backend1 = EmbeddedMessagingBackend(port=port, auto_start_server=False)
        backend2 = EmbeddedMessagingBackend(port=port, auto_start_server=False)

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

        # Test subscription
        received_messages = []

        def handler(message):
            received_messages.append(message)
            print(f"Subscription received: {message.payload}")

        backend2.subscribe("notifications", handler)
        time.sleep(0.3)  # Let subscription register

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

        # Test message retrieval
        all_notifications = backend2.get_messages_for_topic("notifications")
        print(f"Total notifications in topic: {len(all_notifications)}")

        # Cleanup
        backend1.cleanup()
        backend2.cleanup()

    except Exception as e:
        print(f"Error in simple test: {e}")
        raise

    print("Test completed")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "simple":
        run_simple_messaging_test()
    else:
        asyncio.run(run_distributed_example())
