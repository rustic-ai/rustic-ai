# Shared Memory Messaging Backend

The Shared Memory Messaging Backend provides a Redis-like messaging solution for testing distributed agents without requiring external dependencies. It's designed to work with any execution engine and uses only Python standard library components.

## Overview

The shared memory backend consists of two main components:

1. **SharedMemoryServer**: An HTTP-based server that stores messages and provides Redis-like data structures
2. **SharedMemoryMessagingBackend**: A messaging backend that communicates with the server

## Key Features

### Core Messaging Features
- **Message Storage**: Store and retrieve messages by topic
- **Real-time Subscriptions**: Subscribe to topics with real-time notifications via long polling
- **Pattern Subscriptions**: Subscribe to topics using Redis-style patterns (`*` and `?` wildcards)
- **Message TTL**: Automatic expiration of messages after a specified time
- **Cross-Process Communication**: Multiple processes can share the same server

### Redis-like Data Structures
- **Strings**: Key-value storage with optional expiration
- **Hashes**: Hash maps for structured data
- **Sets**: Unordered collections of unique items
- **Pub/Sub**: Publish-subscribe messaging with pattern support

### Testing Features
- **No External Dependencies**: Uses only Python standard library
- **Automatic Port Assignment**: Finds free ports automatically
- **Easy Cleanup**: Proper resource management and cleanup
- **Thread-safe**: Safe for use across multiple threads
- **Process-safe**: Safe for use across multiple processes

## Basic Usage

### Simple Setup

```python
from rustic_ai.core.messaging.backend.shared_memory_backend import (
    SharedMemoryMessagingBackend,
    start_shared_memory_server
)

# Auto-start server (simplest approach)
backend = SharedMemoryMessagingBackend()

# Or use external server
server, url = start_shared_memory_server()
backend = SharedMemoryMessagingBackend(server_url=url, auto_start_server=False)
```

### With MessagingConfig

```python
from rustic_ai.core.messaging.core.messaging_config import MessagingConfig
from rustic_ai.core.messaging.backend.shared_memory_backend import create_shared_messaging_config

# Create config
config_dict = create_shared_messaging_config()
messaging_config = MessagingConfig(**config_dict)

# Use with Guild
guild = Guild(
    guild_id="test_guild",
    execution_engine=SyncExecutionEngine(),
    messaging_config=messaging_config
)
```

## Advanced Usage

### Distributed Testing

```python
# Start a shared server for multiple processes
server, url = start_shared_memory_server()

# In process 1
backend1 = SharedMemoryMessagingBackend(url, auto_start_server=False)

# In process 2  
backend2 = SharedMemoryMessagingBackend(url, auto_start_server=False)

# Both backends share the same message store
```

### Real-time Subscriptions

```python
def message_handler(message):
    print(f"Received: {message.payload}")

# Subscribe to topic
backend.subscribe("notifications", message_handler)

# Messages stored to this topic will trigger the handler
backend.store_message("namespace", "notifications", message)
```

### Pattern Subscriptions

```python
def pattern_handler(message):
    print(f"Pattern match: {message.payload}")

# Subscribe to pattern (Redis-style)
backend.psubscribe("sensor.*", pattern_handler)

# Matches: sensor.temperature, sensor.humidity, etc.
backend.store_message("ns", "sensor.temperature", message)
```

### Redis-like Operations

```python
# String operations
backend.set("key", "value", ex=60)  # Expires in 60 seconds
value = backend.get("key")

# Hash operations
backend.hset("user:123", "name", "John")
backend.hset("user:123", "email", "john@example.com")
name = backend.hget("user:123", "name")

# Set operations
backend.sadd("active_users", "user1", "user2", "user3")
users = backend.smembers("active_users")

# Pub/Sub
count = backend.publish("alerts", "System maintenance starting")
```

## Testing Utilities

### Pytest Fixtures

```python
import pytest
from rustic_ai.testing.messaging.shared_memory import (
    shared_memory_server,
    shared_messaging_config,
    shared_messaging_backend
)

def test_messaging(shared_messaging_backend):
    backend = shared_messaging_backend
    # Test your messaging logic
    backend.store_message("test", "topic", message)
    messages = backend.get_messages_for_topic("topic")
    assert len(messages) == 1
```

### Test Helpers

```python
from rustic_ai.testing.messaging.shared_memory import (
    SharedMemoryTestHelper,
    DistributedTestScenario
)

# Simple helper
with SharedMemoryTestHelper() as helper:
    backend = helper.get_backend()
    # Test messaging

# Distributed scenario
with DistributedTestScenario() as scenario:
    backend1 = scenario.create_backend("agent1")
    backend2 = scenario.create_backend("agent2")
    
    scenario.setup_subscriber("agent1", "topic")
    # Send message from agent2, verify agent1 receives it
```

## Configuration Options

### Server Configuration

```python
server = SharedMemoryServer(
    host="localhost",  # Server host
    port=0,           # Port (0 = auto-assign)
)
```

### Backend Configuration

```python
backend = SharedMemoryMessagingBackend(
    server_url="http://localhost:8080",  # Server URL
    auto_start_server=True,              # Auto-start if no URL
)
```

### MessagingConfig Integration

```python
config = {
    "backend_module": "rustic_ai.core.messaging.backend.shared_memory_backend",
    "backend_class": "SharedMemoryMessagingBackend",
    "backend_config": {
        "server_url": "http://localhost:8080",
        "auto_start_server": False
    }
}
```

## API Reference

### SharedMemoryServer

#### Methods

- `start() -> str`: Start server and return URL
- `stop()`: Stop the server
- `cleanup()`: Clear all stored data

#### Endpoints

- `GET /health`: Health check
- `GET /stats`: Server statistics
- `POST /store_message`: Store a message
- `GET /messages/{topic}`: Get all messages for topic
- `POST /subscribe`: Subscribe to topic
- `POST /publish`: Publish message to channel
- `POST /set`: Redis SET command
- `GET /get/{key}`: Redis GET command

### SharedMemoryMessagingBackend

#### Core Methods

- `store_message(namespace, topic, message)`: Store a message
- `get_messages_for_topic(topic)`: Get all messages for topic
- `get_messages_since(topic, msg_id)`: Get messages since ID
- `subscribe(topic, handler)`: Subscribe to topic
- `unsubscribe(topic)`: Unsubscribe from topic

#### Redis-like Methods

- `set(key, value, ex=None)`: Set string value
- `get(key)`: Get string value
- `hset(key, field, value)`: Set hash field
- `hget(key, field)`: Get hash field
- `sadd(key, *members)`: Add to set
- `smembers(key)`: Get set members
- `publish(channel, message)`: Publish message
- `psubscribe(pattern, handler)`: Pattern subscribe

## Performance Considerations

### Scalability
- **Memory Usage**: All data stored in memory, suitable for testing
- **Concurrent Connections**: HTTP server handles multiple connections
- **Message Volume**: Designed for test scenarios, not production scale

### Limitations
- **Persistence**: Data is lost when server stops
- **Network Overhead**: HTTP-based communication has overhead
- **Single Server**: No clustering or replication

## Best Practices

### For Testing

1. **Use Fixtures**: Leverage pytest fixtures for consistent setup
2. **Cleanup Resources**: Always cleanup backends and servers
3. **Isolated Tests**: Use separate servers for independent tests
4. **Timeout Handling**: Set appropriate timeouts for async operations

### For Development

1. **Auto-start for Simple Cases**: Use auto-start for single-process tests
2. **Shared Server for Complex Cases**: Use shared server for multi-process tests
3. **Pattern Subscriptions**: Use patterns for flexible topic matching
4. **TTL for Cleanup**: Use message TTL to prevent memory leaks

### Error Handling

```python
try:
    backend = SharedMemoryMessagingBackend(
        server_url="http://localhost:8080",
        auto_start_server=False
    )
except ConnectionError:
    # Handle server connection failure
    print("Could not connect to shared memory server")
```

## Examples

### Basic Message Exchange

```python
from rustic_ai.core.messaging.core.message import Message, AgentTag
from rustic_ai.core.utils.gemstone_id import GemstoneGenerator

# Setup
backend = SharedMemoryMessagingBackend()
generator = GemstoneGenerator(1)

# Create message
message = Message(
    id_obj=generator.get_id(),
    sender=AgentTag(id="sender", name="Sender"),
    topics="test_topic",
    payload={"data": "Hello World"}
)

# Store and retrieve
backend.store_message("test", "test_topic", message)
messages = backend.get_messages_for_topic("test_topic")
print(f"Retrieved: {messages[0].payload}")
```

### Multi-Process Coordination

```python
# Process 1: Coordinator
server, url = start_shared_memory_server()
coordinator_backend = SharedMemoryMessagingBackend(url, auto_start_server=False)

# Assign work
coordinator_backend.set("task_1", "process_data")
coordinator_backend.sadd("pending_tasks", "task_1")

# Process 2: Worker
worker_backend = SharedMemoryMessagingBackend(url, auto_start_server=False)

# Get work
task = worker_backend.get("task_1")
pending = worker_backend.smembers("pending_tasks")
print(f"Processing: {task}")
```

### Real-time Notifications

```python
notifications = []

def notification_handler(message):
    notifications.append(message.payload)

# Subscribe
backend.subscribe("alerts", notification_handler)

# Send notification (from another process/thread)
alert_message = Message(
    id_obj=generator.get_id(),
    sender=AgentTag(id="system", name="System"),
    topics="alerts",
    payload={"type": "warning", "message": "High CPU usage"}
)
backend.store_message("system", "alerts", alert_message)

# Handler will be called automatically
```

## Troubleshooting

### Common Issues

1. **Connection Refused**: Server not started or wrong URL
2. **Port Already in Use**: Specify different port or use auto-assignment
3. **Messages Not Received**: Check subscription setup and polling
4. **Memory Growth**: Use TTL or periodic cleanup

### Debugging

```python
# Check server status
response = backend._make_request("GET", "/stats")
print(f"Server stats: {response}")

# Check subscriptions
print(f"Local handlers: {backend.local_handlers}")

# Check server health
try:
    backend._test_connection()
    print("Server connection OK")
except ConnectionError as e:
    print(f"Connection error: {e}")
```

## Migration from Redis

The shared memory backend provides Redis-compatible operations for easy migration:

```python
# Redis code
redis_client.set("key", "value")
redis_client.hset("hash", "field", "value")
redis_client.sadd("set", "member")

# Shared memory equivalent
backend.set("key", "value")
backend.hset("hash", "field", "value")
backend.sadd("set", "member")
```

## Conclusion

The Shared Memory Messaging Backend provides a powerful, Redis-like messaging solution for testing distributed agents without external dependencies. It's designed to be easy to use, feature-rich, and suitable for a wide range of testing scenarios while maintaining compatibility with the existing Rustic AI messaging architecture. 