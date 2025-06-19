#!/usr/bin/env python3
"""
Simple test of the EmbeddedMessagingBackend functionality.
"""

import asyncio
import threading
import time

from rustic_ai.core.messaging import Priority
from rustic_ai.core.messaging.backend.embedded_backend import (
    EmbeddedMessagingBackend,
    EmbeddedServer,
)
from rustic_ai.core.messaging.core.message import AgentTag, Message
from rustic_ai.core.utils.gemstone_id import GemstoneGenerator


def start_server_thread(port=31141):
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


def test_basic_messaging():
    """Test basic message storage and retrieval."""
    print("Testing basic messaging...")

    # Start server on a fixed port for examples
    port = start_server_thread(31141)
    print(f"Server started on port: {port}")

    try:
        # Create two backends
        backend1 = EmbeddedMessagingBackend(port=port, auto_start_server=False)
        backend2 = EmbeddedMessagingBackend(port=port, auto_start_server=False)

        # Test basic messaging
        generator = GemstoneGenerator(1)

        # Backend1 sends message
        msg = Message(
            id_obj=generator.get_id(Priority.NORMAL),
            sender=AgentTag(id="sender1", name="Sender 1"),
            topics="test_topic",
            payload={"message": "Hello from backend1!"}
        )
        backend1.store_message("test", "test_topic", msg)

        # Backend2 receives message
        messages = backend2.get_messages_for_topic("test_topic")
        print(f"✓ Backend2 received {len(messages)} messages")
        if messages:
            print(f"  Message content: {messages[0].payload}")

        # Test subscription
        received_messages = []

        def handler(message):
            received_messages.append(message)
            print(f"✓ Subscription received: {message.payload}")

        backend2.subscribe("notifications", handler)
        time.sleep(0.3)  # Let subscription register

        # Send notification
        notification = Message(
            id_obj=generator.get_id(Priority.NORMAL),
            sender=AgentTag(id="notifier", name="Notifier"),
            topics="notifications",
            payload={"type": "alert", "message": "System status update"}
        )
        backend1.store_message("test", "notifications", notification)

        time.sleep(0.5)  # Wait for delivery
        print(f"✓ Received {len(received_messages)} notifications via subscription")

        # Test message history
        all_messages = backend2.get_messages_for_topic("test_topic")
        print(f"✓ Total messages in topic: {len(all_messages)}")

        # Test get messages since
        if all_messages:
            recent_messages = backend2.get_messages_for_topic_since("test_topic", all_messages[0].id)
            print(f"✓ Messages since first message: {len(recent_messages)}")

        # Cleanup
        backend1.cleanup()
        backend2.cleanup()

        print("\n✓ All tests completed successfully!")

    except Exception as e:
        print(f"❌ Test failed: {e}")
        raise


def test_distributed_coordination():
    """Test distributed coordination features."""
    print("\nTesting distributed coordination...")

    port = start_server_thread(31142)

    try:
        # Simulate coordinator process
        coordinator = EmbeddedMessagingBackend(port=port, auto_start_server=False)

        # Simulate worker processes
        worker1 = EmbeddedMessagingBackend(port=port, auto_start_server=False)
        worker2 = EmbeddedMessagingBackend(port=port, auto_start_server=False)

        generator = GemstoneGenerator(2)

        # Coordinator assigns tasks via messages
        task1_msg = Message(
            id_obj=generator.get_id(Priority.NORMAL),
            sender=AgentTag(id="coordinator", name="Coordinator"),
            topics="task_assignments",
            payload={"task_id": "task_1", "action": "process_data_batch_1", "assigned_to": "worker1"}
        )

        task2_msg = Message(
            id_obj=generator.get_id(Priority.NORMAL),
            sender=AgentTag(id="coordinator", name="Coordinator"),
            topics="task_assignments",
            payload={"task_id": "task_2", "action": "process_data_batch_2", "assigned_to": "worker2"}
        )

        coordinator.store_message("coordination", "task_assignments", task1_msg)
        coordinator.store_message("coordination", "task_assignments", task2_msg)

        print("✓ Coordinator assigned tasks")

        # Workers pick up tasks
        tasks = worker1.get_messages_for_topic("task_assignments")
        print(f"✓ Worker1 sees {len(tasks)} assigned tasks")

        # Set up result subscriptions
        results = []

        def result_handler(message):
            results.append(message)
            print(f"✓ Coordinator received result: {message.payload}")

        coordinator.subscribe("task_results", result_handler)
        time.sleep(0.3)

        # Workers complete tasks and report results
        result1_msg = Message(
            id_obj=generator.get_id(Priority.NORMAL),
            sender=AgentTag(id="worker1", name="Worker 1"),
            topics="task_results",
            payload={"task_id": "task_1", "status": "completed", "result": "processed_data_batch_1"}
        )

        result2_msg = Message(
            id_obj=generator.get_id(Priority.NORMAL),
            sender=AgentTag(id="worker2", name="Worker 2"),
            topics="task_results",
            payload={"task_id": "task_2", "status": "completed", "result": "processed_data_batch_2"}
        )

        worker1.store_message("coordination", "task_results", result1_msg)
        worker2.store_message("coordination", "task_results", result2_msg)

        print("✓ Workers completed tasks")

        # Wait for results
        time.sleep(0.5)
        print(f"✓ Coordinator received {len(results)} results")

        # Test pub/sub for system notifications
        notifications = []

        def notification_handler(message):
            notifications.append(message)
            print(f"✓ Worker received notification: {message.payload}")

        # All workers subscribe to notifications
        worker1.subscribe("system_notifications", notification_handler)
        worker2.subscribe("system_notifications", notification_handler)
        time.sleep(0.3)

        # Coordinator publishes notification
        notification = Message(
            id_obj=generator.get_id(Priority.NORMAL),
            sender=AgentTag(id="coordinator", name="Coordinator"),
            topics="system_notifications",
            payload={"type": "completion", "message": "All tasks completed!"}
        )
        coordinator.store_message("coordination", "system_notifications", notification)

        time.sleep(0.5)
        print(f"✓ Workers received {len(notifications)} notifications")

        # Cleanup
        coordinator.cleanup()
        worker1.cleanup()
        worker2.cleanup()

        print("✓ Distributed coordination test completed!")

    except Exception as e:
        print(f"❌ Test failed: {e}")
        raise


if __name__ == "__main__":
    test_basic_messaging()
    test_distributed_coordination()
    print("\n🎉 All tests passed!")
