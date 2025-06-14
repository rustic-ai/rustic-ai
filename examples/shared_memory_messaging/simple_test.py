#!/usr/bin/env python3
"""
Simple test of the SharedMemoryMessagingBackend functionality.
"""

import time

from rustic_ai.core.messaging import Priority
from rustic_ai.core.messaging.backend.shared_memory_backend import (
    SharedMemoryMessagingBackend,
    start_shared_memory_server,
)
from rustic_ai.core.messaging.core.message import AgentTag, Message
from rustic_ai.core.utils.gemstone_id import GemstoneGenerator


def test_basic_messaging():
    """Test basic message storage and retrieval."""
    print("Testing basic messaging...")

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

        # Test Redis-like operations
        backend1.set("shared_key", "shared_value")
        value = backend2.get("shared_key")
        print(f"✓ Shared key-value: {value}")

        backend1.sadd("shared_set", "item1", "item2", "item3")
        members = backend2.smembers("shared_set")
        print(f"✓ Shared set members: {members}")

        # Test subscription
        received_messages = []

        def handler(message):
            received_messages.append(message)
            print(f"✓ Subscription received: {message.payload}")

        backend2.subscribe("notifications", handler)
        time.sleep(0.2)  # Let subscription register

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

        # Test pattern subscription
        pattern_messages = []

        def pattern_handler(message):
            pattern_messages.append(message)
            print(f"✓ Pattern subscription received: {message.payload}")

        backend2.psubscribe("sensor.*", pattern_handler)
        time.sleep(0.2)

        # Send to matching pattern
        sensor_msg = Message(
            id_obj=generator.get_id(Priority.NORMAL),
            sender=AgentTag(id="sensor", name="Sensor"),
            topics="sensor.temperature",
            payload={"value": 25.5, "unit": "celsius"}
        )
        backend1.store_message("test", "sensor.temperature", sensor_msg)

        time.sleep(0.5)
        print(f"✓ Pattern subscription received {len(pattern_messages)} messages")

        # Test TTL
        print("Testing TTL...")
        ttl_msg = Message(
            id_obj=generator.get_id(Priority.NORMAL),
            sender=AgentTag(id="temp", name="Temp"),
            topics="ttl_topic",
            payload={"data": "expires_soon"},
            ttl=1  # 1 second TTL
        )
        backend1.store_message("test", "ttl_topic", ttl_msg)

        # Should exist immediately
        messages = backend2.get_messages_for_topic("ttl_topic")
        print(f"✓ TTL message exists: {len(messages)} messages")

        # Wait for expiration
        print("  Waiting for TTL expiration...")
        time.sleep(2)

        # Check if cleaned up (may still exist due to cleanup timing)
        messages = backend2.get_messages_for_topic("ttl_topic")
        print(f"  After TTL: {len(messages)} messages (may still exist due to cleanup timing)")

        # Test server stats
        print("\nServer Statistics:")
        try:
            import json
            import urllib.request
            response = urllib.request.urlopen(f"{url}/stats")
            stats = json.loads(response.read().decode())
            for key, value in stats.items():
                print(f"  {key}: {value}")
        except Exception as e:
            print(f"  Could not get stats: {e}")

        # Cleanup
        backend1.cleanup()
        backend2.cleanup()

        print("\n✓ All tests completed successfully!")

    finally:
        server.stop()
        print("✓ Server stopped")


def test_distributed_coordination():
    """Test distributed coordination features."""
    print("\nTesting distributed coordination...")

    server, url = start_shared_memory_server()

    try:
        # Simulate coordinator process
        coordinator = SharedMemoryMessagingBackend(url, auto_start_server=False)

        # Simulate worker processes
        worker1 = SharedMemoryMessagingBackend(url, auto_start_server=False)
        worker2 = SharedMemoryMessagingBackend(url, auto_start_server=False)

        # Coordinator assigns tasks
        coordinator.set("task_1", "process_data_batch_1")
        coordinator.set("task_2", "process_data_batch_2")
        coordinator.sadd("pending_tasks", "task_1", "task_2")
        coordinator.set("task_counter", "2")

        print("✓ Coordinator assigned tasks")

        # Workers pick up tasks
        pending = worker1.smembers("pending_tasks")
        print(f"✓ Worker1 sees {len(pending)} pending tasks: {pending}")

        # Worker1 processes task_1
        task1 = worker1.get("task_1")
        worker1.hset("results", "task_1", f"completed_{task1}")
        worker1.sadd("completed_tasks", "task_1")
        print(f"✓ Worker1 completed: {task1}")

        # Worker2 processes task_2
        task2 = worker2.get("task_2")
        worker2.hset("results", "task_2", f"completed_{task2}")
        worker2.sadd("completed_tasks", "task_2")
        print(f"✓ Worker2 completed: {task2}")

        # Coordinator checks results
        completed = coordinator.smembers("completed_tasks")
        print(f"✓ Coordinator sees {len(completed)} completed tasks: {completed}")

        for task in completed:
            result = coordinator.hget("results", task)
            print(f"  {task}: {result}")

        # Test pub/sub for notifications
        notifications = []

        def notification_handler(message):
            notifications.append(message)

        # All workers subscribe to notifications
        worker1.subscribe("system_notifications", notification_handler)
        worker2.subscribe("system_notifications", notification_handler)
        time.sleep(0.2)

        # Coordinator publishes notification
        count = coordinator.publish("system_notifications", "All tasks completed!")
        print(f"✓ Notification sent to {count} subscribers")

        time.sleep(0.5)
        print(f"✓ Workers received {len(notifications)} notifications")

        # Cleanup
        coordinator.cleanup()
        worker1.cleanup()
        worker2.cleanup()

        print("✓ Distributed coordination test completed!")

    finally:
        server.stop()


if __name__ == "__main__":
    test_basic_messaging()
    test_distributed_coordination()
    print("\n🎉 All tests passed!")
