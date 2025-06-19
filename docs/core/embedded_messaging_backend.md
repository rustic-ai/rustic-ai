# Embedded Messaging Backend

The Embedded Messaging Backend provides a fast, embedded messaging solution for testing distributed agents without requiring external dependencies. It's designed to work with any execution engine and uses only Python standard library components with asyncio for high performance.

## Overview

The embedded messaging backend consists of two main components:

1. **EmbeddedServer**: A TCP socket-based server that stores messages and provides real-time messaging
2. **EmbeddedMessagingBackend**: A messaging backend that communicates with the server via socket connections

## Key Features

### Core Messaging Features
- **Message Storage**: Store and retrieve messages by topic
- **Real-time Subscriptions**: Subscribe to topics with true push delivery via asyncio
- **Message TTL**: Automatic expiration of messages after a specified time
- **Cross-Process Communication**: Multiple processes can share the same server
- **Back-pressure Handling**: Per-connection message queues with overflow protection
- **Thread Safety**: Designed for multi-threaded and multi-process environments

### Performance Features
- **Socket-Based**: Direct TCP socket communication for minimal latency
- **Asyncio Integration**: Non-blocking operations with event loop efficiency
- **Connection Pooling**: Efficient connection management
- **Binary Protocol**: Fast text-based wire protocol with base64 encoding

### Testing Features
- **No External Dependencies**: Uses only Python standard library
- **Fixed Port Configuration**: Predictable ports for testing scenarios
- **Easy Cleanup**: Proper resource management and cleanup
- **Thread-safe**: Safe for use across multiple threads
- **Process-safe**: Safe for use across multiple processes

## Basic Usage

### Simple Setup

```python
from rustic_ai.core.messaging.backend.embedded_backend import (
    EmbeddedMessagingBackend,
    EmbeddedServer
)

# Auto-start server (simplest approach)
backend = EmbeddedMessagingBackend()

# Or use external server
port = 31134
backend = EmbeddedMessagingBackend(port=port, auto_start_server=False)
```

### With MessagingConfig

```python
from rustic_ai.core.messaging.core.messaging_config import MessagingConfig
from rustic_ai.core.messaging.backend.embedded_backend import create_embedded_messaging_config

# Create config
config_dict = create_embedded_messaging_config()
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
import asyncio
import threading

def start_server(port=31134):
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
    return port

# In process 1
port = start_server(31134)
backend1 = EmbeddedMessagingBackend(port=port, auto_start_server=False)

# In process 2  
backend2 = EmbeddedMessagingBackend(port=port, auto_start_server=False)

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

### Message-based Coordination

```python
from rustic_ai.core.messaging.core.message import Message, AgentTag
from rustic_ai.core.utils.gemstone_id import GemstoneGenerator

generator = GemstoneGenerator(1)

# Coordination via messages
status_msg = Message(
    id_obj=generator.get_id(),
    sender=AgentTag(id="coordinator", name="Coordinator"),
    topics="task_status",
    payload={"task_id": "task_1", "status": "assigned", "worker": "worker_1"}
)
backend.store_message("coordination", "task_status", status_msg)

# Workers can retrieve coordination messages
messages = backend.get_messages_for_topic("task_status")
```

## Testing Utilities

### Pytest Fixtures

```python
import pytest
from rustic_ai.testing.messaging.shared_memory import (
    socket_messaging_server,
    socket_messaging_config,
    socket_messaging_backend
)

def test_messaging(socket_messaging_backend):
    backend = socket_messaging_backend
    # Test your messaging logic
    backend.store_message("test", "topic", message)
    messages = backend.get_messages_for_topic("topic")
    assert len(messages) == 1
```

### Test Helpers

```python
from rustic_ai.testing.messaging.shared_memory import (
    SocketMessagingTestHelper,
    DistributedTestScenario
)

# Simple helper
with SocketMessagingTestHelper() as helper:
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
server = EmbeddedServer(
    port=31134,  # Fixed port (required)
)
```

### Backend Configuration

```python
backend = EmbeddedMessagingBackend(
    port=31134,           # Server port
    auto_start_server=True,  # Auto-start if server not running
)
```

### MessagingConfig Integration

```python
config = {
    "backend_module": "rustic_ai.core.messaging.backend.embedded_backend",
    "backend_class": "EmbeddedMessagingBackend",
    "backend_config": {
        "port": 31134,
        "auto_start_server": False
    }
}
```

## API Reference

### EmbeddedServer

#### Methods

- `async start()`: Start the asyncio server
- `async stop()`: Stop the server
- `get_stats()`: Get server statistics

#### Socket Protocol

The server uses a text-based protocol with base64 encoding:

```
COMMAND arg1 arg2 ...
```

Supported commands:
- `PUBLISH topic message_json`
- `SUBSCRIBE topic`
- `UNSUBSCRIBE topic`
- `STORE_MESSAGE namespace topic message_json`
- `GET_MESSAGES topic`
- `GET_MESSAGES_SINCE topic message_id`
- `GET_MESSAGES_BY_ID namespace message_ids_json`

### EmbeddedMessagingBackend

#### Core Methods

- `store_message(namespace, topic, message)`: Store a message
- `get_messages_for_topic(topic)`: Get all messages for topic
- `get_messages_for_topic_since(topic, msg_id)`: Get messages since ID
- `get_messages_by_id(namespace, msg_ids)`: Get messages by ID list
- `subscribe(topic, handler)`: Subscribe to topic
- `unsubscribe(topic)`: Unsubscribe from topic
- `supports_subscription()`: Check if backend supports subscriptions
- `load_subscribers(subscribers)`: Load subscriber configuration

## Performance Characteristics

### Scalability
- **Memory Usage**: All data stored in memory, suitable for testing
- **Concurrent Connections**: Asyncio handles multiple connections efficiently
- **Message Volume**: Designed for test scenarios with good performance
- **Latency**: ~0.1-1ms typical latency for local socket communication

### Advantages over HTTP-based
- **Lower Latency**: Direct socket communication vs HTTP overhead
- **True Push**: Real-time message delivery vs polling
- **Connection Efficiency**: Persistent connections vs request/response cycles
- **Back-pressure**: Built-in queue management vs connection timeouts

### Limitations
- **Persistence**: Data is lost when server stops
- **Single Server**: No clustering or replication
- **Local Only**: Designed for single-machine testing

## Best Practices

### For Testing

1. **Use Fixed Ports**: Use predictable ports for test reproducibility
2. **Use Fixtures**: Leverage pytest fixtures for consistent setup
3. **Cleanup Resources**: Always cleanup backends and servers
4. **Isolated Tests**: Use separate ports for independent tests
5. **Timeout Handling**: Set appropriate timeouts for async operations

### For Development

1. **Auto-start for Simple Cases**: Use auto-start for single-process tests
2. **Shared Server for Complex Cases**: Use shared server for multi-process tests
3. **Message-based Coordination**: Use messages for process coordination
4. **TTL for Cleanup**: Use message TTL to prevent memory leaks

### Error Handling

```python
try:
    backend = SocketMessagingBackend(
        port=31134,
        auto_start_server=False
    )
except ConnectionError:
    # Handle server connection failure
    print("Could not connect to socket messaging server")
```

## Examples

### Basic Message Exchange

```python
from rustic_ai.core.messaging.core.message import Message, AgentTag
from rustic_ai.core.utils.gemstone_id import GemstoneGenerator

# Setup
backend = EmbeddedMessagingBackend()
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
from rustic_ai.core.messaging.core.message import Message, AgentTag
from rustic_ai.core.utils.gemstone_id import GemstoneGenerator

# Process 1: Coordinator
backend = EmbeddedMessagingBackend(port=31134)
generator = GemstoneGenerator(1)

# Assign work via messages
task_msg = Message(
    id_obj=generator.get_id(),
    sender=AgentTag(id="coordinator", name="Coordinator"),
    topics="task_assignments",
    payload={"task_id": "task_1", "action": "process_data", "worker": "worker_1"}
)
backend.store_message("coordination", "task_assignments", task_msg)

# Process 2: Worker
worker_backend = EmbeddedMessagingBackend(port=31134, auto_start_server=False)

# Get work assignments
tasks = worker_backend.get_messages_for_topic("task_assignments")
for task in tasks:
    if task.payload.get("worker") == "worker_1":
        print(f"Processing: {task.payload['action']}")
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

# Handler will be called automatically via socket push
```

## Troubleshooting

### Common Issues

1. **Connection Refused**: Server not started or wrong port
2. **Port Already in Use**: Specify different port
3. **Messages Not Received**: Check subscription setup and connection
4. **Memory Growth**: Use TTL or periodic cleanup

### Debugging

```python
# Test connection
try:
    backend._test_connection()
    print("Server connection OK")
except ConnectionError as e:
    print(f"Connection error: {e}")

# Check subscriptions
print(f"Active subscriptions: {list(backend.local_handlers.keys())}")

# Check message counts
messages = backend.get_messages_for_topic("test_topic")
print(f"Messages in topic: {len(messages)}")
```

## Migration from HTTP-based Backends

The socket messaging backend provides improved performance over HTTP-based messaging:

```python
# Old HTTP-based approach
backend.subscribe("topic", handler)  # Long polling
backend.store_message("ns", "topic", msg)  # HTTP POST

# New socket-based approach (same API, better performance)
backend.subscribe("topic", handler)  # Real-time push
backend.store_message("ns", "topic", msg)  # Socket command
```

## Comparison with Other Backends

| Feature | InMemory | EmbeddedMessaging | Redis |
|---------|----------|-----------------|-------|
| **Latency** | ~1μs | ~0.1-1ms | ~1-10ms |
| **Cross-Process** | No | Yes | Yes |
| **Real-time** | Immediate | Push delivery | Near real-time |
| **Dependencies** | None | None | Redis Server |
| **Persistence** | None | None | Full |
| **Scalability** | Single process | Multi-process | Distributed |

## Conclusion

The Embedded Messaging Backend provides a high-performance, embedded messaging solution for testing distributed agents without external dependencies. It offers significant performance improvements over HTTP-based approaches while maintaining the simplicity and zero-dependency philosophy. The backend is designed to be easy to use, feature-rich, and suitable for a wide range of testing scenarios while maintaining compatibility with the existing Rustic AI messaging architecture. 