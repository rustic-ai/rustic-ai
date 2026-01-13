# Messaging

The messaging system in Rustic AI enables asynchronous, topic-based communication between agents within guilds. It provides a layered architecture with pluggable backends for different deployment scenarios, from development to distributed production systems.

## Purpose
- Facilitate communication between agents within and across guilds
- Support topic-based publish/subscribe messaging with namespace isolation
- Enable message persistence, retrieval, and real-time notifications
- Provide pluggable storage backends for different deployment needs

## Architecture Overview

The messaging system consists of three main layers:

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│     Clients     │───▶│ MessagingInterface│───▶│ MessagingBackend│
│   (Agents)      │    │  (Message Bus)   │    │   (Storage)     │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

## Key Concepts

### Messages
Structured data packets exchanged between agents with the following key properties:
- **Unique IDs**: Generated using `GemstoneID` with embedded timestamp and priority
- **Topics**: Support single or multiple topic publishing
- **Threading**: Maintain conversation threads and message history
- **Namespacing**: Automatic namespace isolation per guild

### Topics
Channels for message delivery with automatic namespace prefixing:
- **Guild Isolation**: Each guild gets its own namespace (e.g., `guild-123:topic-name`)
- **Subscription Management**: Agents subscribe to topics to receive relevant messages
- **Multi-Topic Publishing**: Single message can be published to multiple topics

### Clients
Agents interact with the messaging system via client interfaces:
- **MessageTrackingClient**: Default client with message ordering and tracking
- **SimpleClient**: Basic client for simple use cases
- **Specialized Clients**: Pipeline, filtering, throttling, and other decorators

### Backends
Pluggable storage implementations:
- **InMemoryMessagingBackend**: Fast, in-memory storage for development/testing
- **RedisMessagingBackend**: Persistent, distributed storage for production
- **Custom Backends**: Implement `MessagingBackend` interface for specialized needs

## Message Schema

Every `Message` instance has the following structure:

```python
class Message(BaseModel):
    # Core fields
    sender: AgentTag                    # Who sent the message
    topics: Union[str, List[str]]       # Target topic(s)
    payload: JsonDict                   # Message content
    format: str                         # Message format (default: "generic_json")
    
    # Optional fields
    recipient_list: List[AgentTag]      # Tagged recipients
    in_response_to: Optional[int]       # Reply to message ID
    thread: List[int]                   # Conversation thread
    conversation_id: Optional[int]      # Conversation grouping
    forward_header: Optional[ForwardHeader]  # Forwarding information
    routing_slip: Optional[RoutingSlip] # Multi-step routing
    message_history: List[ProcessEntry] # Processing history
    ttl: Optional[int]                  # Time to live
    
    # Computed fields (read-only)
    id: int                            # Unique message ID
    priority: Priority                 # Message priority (0-9)
    timestamp: float                   # Creation timestamp
```

### JSON Serialization Example
```json
{
  "id": 123456789,
  "sender": {"id": "agent-1", "name": "Agent One"},
  "topics": "updates",
  "payload": {"text": "Hello, World!"},
  "format": "generic_json",
  "priority": 4,
  "timestamp": 1640995200.123,
  "thread": [123456789],
  "recipient_list": [],
  "in_response_to": null,
  "conversation_id": null,
  "forward_header": null,
  "routing_slip": null,
  "message_history": [],
  "ttl": null,
  "is_error_message": false,
  "traceparent": null,
  "session_state": null,
  "topic_published_to": "updates",
  "enrich_with_history": 0
}
```

## MessagingInterface: The Message Bus

The `MessagingInterface` serves as the central message bus with the following responsibilities:

### Client Management
```python
# Register agent as messaging client
messaging.register_client(client)

# Unregister when agent shuts down
messaging.unregister_client(client)
```

### Topic Subscription
```python
# Subscribe agent to topic
messaging.subscribe("updates", client)

# Unsubscribe from topic
messaging.unsubscribe("updates", client)
```

### Message Publishing
```python
# Publish message to topic(s)
messaging.publish(sender_client, message)
```

### Message Retrieval
```python
# Get all messages for a topic
messages = messaging.get_messages("updates")

# Get messages since specific ID
recent_messages = messaging.get_messages_for_topic_since("updates", last_id)

# Get messages for a specific client across all subscribed topics
client_messages = messaging.get_messages_for_client_since(client_id, last_id)
```

### Advanced Features

#### Namespace Isolation
- Automatic topic prefixing: `topic` → `guild-123:topic`
- Prevents message leakage between guilds
- Transparent to agents

#### Message History Enrichment
```python
# Messages can request conversation history
message.enrich_with_history = 5  # Include last 5 messages
# History automatically added to message.session_state["enriched_history"]
```

#### Smart Subscription Management
- Lazy backend subscription (only when first client subscribes)
- Reference counting (unsubscribe from backend when last client leaves)
- Automatic cleanup on client disconnect

## MessagingBackend: Storage Layer

The `MessagingBackend` abstract base class defines the interface for message storage:

### Core Interface
```python
class MessagingBackend(ABC):
    @abstractmethod
    def store_message(self, namespace: str, topic: str, message: Message) -> None:
        """Store a message in the backend"""
    
    @abstractmethod
    def get_messages_for_topic(self, topic: str) -> List[Message]:
        """Retrieve all messages for a topic"""
    
    @abstractmethod
    def get_messages_for_topic_since(self, topic: str, msg_id_since: int) -> List[Message]:
        """Retrieve messages since a specific ID"""
    
    @abstractmethod
    def subscribe(self, topic: str, handler: Callable[[Message], None]) -> None:
        """Subscribe to real-time notifications"""
    
    @abstractmethod
    def get_messages_by_id(self, namespace: str, msg_ids: List[int]) -> List[Message]:
        """Batch retrieve messages by ID"""
```

### Available Backends

#### InMemoryMessagingBackend
```python
# Configuration
MessagingConfig(
    backend_module="rustic_ai.core.messaging.backend",
    backend_class="InMemoryMessagingBackend",
    backend_config={}
)
```

**Features:**

- **Performance**: Extremely fast in-memory operations
- **Real-time**: Immediate callback-based notifications
- **Singleton**: Shared state across multiple interface instances
- **Development**: Perfect for testing and development

**Limitations:**

- **Not Persistent**: Data lost on restart
- **Single Process**: Cannot share across processes
- **Memory Bound**: Limited by available RAM

#### RedisMessagingBackend
```python
# Configuration
MessagingConfig(
    backend_module="rustic_ai.redis.messaging.backend",
    backend_class="RedisMessagingBackend",
    backend_config={
        "redis_client": {
            "host": "localhost",
            "port": 6379,
            "ssl": False
        }
    }
)
```

**Features:**

- **Persistent**: Data survives restarts
- **Distributed**: Shared across processes and machines
- **Scalable**: Redis clustering support
- **Real-time**: Redis pub/sub for notifications
- **TTL Support**: Configurable message expiration
- **Efficient**: Pipeline operations for batch processing

**Storage Strategy:**

- **Sorted Sets**: Messages stored with timestamp scores for ordering
- **Secondary Index**: Direct ID lookup via `msg:namespace:id` keys
- **Pub/Sub**: Real-time notifications via Redis pub/sub

## Configuration

### MessagingConfig
```python
class MessagingConfig(BaseModel):
    backend_module: str      # Python module containing backend
    backend_class: str       # Backend class name
    backend_config: Dict     # Backend-specific configuration
```

### Dynamic Backend Creation
```python
# MessagingConfig automatically creates backend instances
config = MessagingConfig(
    backend_module="rustic_ai.core.messaging.backend",
    backend_class="InMemoryMessagingBackend",
    backend_config={}
)

# MessagingInterface uses config to create backend
messaging = MessagingInterface(namespace="guild-123", messaging_config=config)
```

## Message Flow Example

```python
# 1. Agent A sends message
message = Message(
    id_obj=generator.get_id(Priority.NORMAL),
    sender=AgentTag(id="agent-a", name="Agent A"),
    topics="updates",
    payload={"text": "Hello, Agent B!"}
)

# 2. Publish via messaging interface
messaging_interface.publish(client_a, message)

# 3. MessagingInterface processes:
#    - Adds namespace prefix: "updates" → "guild-123:updates"
#    - Stores in backend
#    - Notifies subscribers

# 4. Backend stores and notifies:
#    - InMemory: Immediate callback
#    - Redis: Pub/sub notification

# 5. Agent B receives message:
#    - Client notified via callback
#    - Message delivered to agent's message handler
```

### Cross-Process Messaging Example

```python
# Process 1: Setup Redis messaging backend with MultiProcessExecutionEngine
from rustic_ai.core.guild.execution.multiprocess import MultiProcessExecutionEngine

# Create messaging config for cross-process communication
messaging_config = MessagingConfig(
    backend_module="rustic_ai.redis.messaging.backend",
    backend_class="RedisMessagingBackend",
    backend_config={
        "redis_client": {
            "host": "localhost",
            "port": 6379,
            "ssl": False
        }
    }
)

# Create guild with multiprocess execution
guild = Guild(
    guild_id="distributed-guild",
    execution_engine=MultiProcessExecutionEngine(guild_id="distributed-guild"),
    messaging_config=messaging_config
)

# Launch agents in separate processes
for i in range(3):
    agent_spec = create_worker_agent_spec(f"worker-{i}")
    guild.launch_agent(agent_spec)

# Agents can now communicate across processes via Redis messaging backend
# - Process isolation maintained
# - Real-time messaging via Redis pub/sub
```

## Client Types

### MessageTrackingClient (Default)

```python
class MessageTrackingClient(Client):
    """Tracks message processing with ordering and deduplication"""
```

- **Message Ordering**: Processes messages in ID order
- **Tracking**: Tracks last processed message ID
- **Threading**: Uses events and heaps for efficient processing

### SimpleClient
```python
class SimpleClient(Client):
    """Basic client for simple messaging needs"""
```
- **Lightweight**: Minimal overhead
- **Direct**: Immediate message processing

### Specialized Clients
- **PipelineClient**: Chain multiple processing steps
- **FilteringClient**: Filter messages based on criteria
- **ThrottlingClient**: Rate-limit message processing
- **RetryingClient**: Automatic retry on failures
- **LoggingClient**: Add logging to message processing

## Integration with Execution Engines

### Execution Engine Compatibility

Different execution engines work optimally with different messaging backends:

| Execution Engine | Recommended Backend | Reason |
|------------------|-------------------|---------|
| `SyncExecutionEngine` | `InMemoryMessagingBackend` | Fast, single-process operation |
| `MultiThreadedEngine` | `InMemoryMessagingBackend` or `RedisMessagingBackend` | Thread-safe with shared memory |
| `MultiProcessExecutionEngine` | `RedisMessagingBackend` | Cross-process communication |
| `RayExecutionEngine` | `RedisMessagingBackend` | Distributed messaging |

### Execution Engine Responsibilities
- **Configuration**: Provide `MessagingConfig` to agent wrappers
- **Lifecycle**: Coordinate messaging setup during agent initialization
- **Isolation**: Each agent gets its own messaging client

### Agent Wrapper Integration
```python
class AgentWrapper:
    def initialize_agent(self):
        # Create MessagingInterface from config
        self.messaging = MessagingInterface(self.agent.guild_id, self.messaging_config)
        
        # Create and register client
        client = self.client_type(
            id=self.agent.id,
            name=self.agent.name,
            message_handler=self.agent._on_message
        )
        self.messaging.register_client(client)
        
        # Subscribe to agent's topics
        for topic in self.agent.subscribed_topics:
            self.messaging.subscribe(topic, client)
```

## Performance Characteristics

### MessagingInterface Performance
- **Client Lookup**: O(1) by client ID
- **Topic Subscription**: O(1) for subscription management
- **Message Copying**: Deep copies for isolation (memory overhead)
- **Namespace Processing**: O(1) string operations

### Backend Performance Comparison

| Feature | InMemoryBackend | RedisBackend |
|---------|----------------|--------------|
| **Latency** | ~1μs | ~1-10ms |
| **Throughput** | Very High | High |
| **Persistence** | None | Full |
| **Scalability** | Single Process | Distributed |
| **Memory Usage** | High (all in RAM) | Low (Redis manages) |
| **Real-time** | Immediate | Near real-time |
| **Cross-Process** | No | Yes |
| **External Dependencies** | None | Redis Server |

## Best Practices

### Development
- Use `InMemoryMessagingBackend` for fast iteration and single-process testing
- Enable debug logging for message flow visibility
- Use `SyncExecutionEngine` for deterministic testing

### Testing
- Use `InMemoryMessagingBackend` for fast, reliable testing
- Use `RedisMessagingBackend` with `MultiProcessExecutionEngine` for realistic distributed testing
- Use real-time subscriptions for responsive test monitoring
- Ensure proper cleanup for test isolation

### Production
- Use `RedisMessagingBackend` for persistence and scalability
- Configure appropriate message TTL to manage storage
- Use `MultiThreadedEngine` or `RayExecutionEngine` for concurrency
- Monitor Redis memory usage and performance

### Message Design
- Keep payloads reasonably sized (< 1MB recommended)
- Use meaningful topic names with clear hierarchy
- Include correlation IDs for request/response patterns
- Leverage message threading for conversation tracking

## Error Handling

### Message Validation
- Pydantic-based validation for message structure
- Automatic type checking and conversion
- Clear error messages for invalid data

### Backend Failures
- MessagingInterface handles backend initialization errors
- Graceful degradation when backend unavailable
- Proper cleanup on shutdown

### Client Disconnection
- Automatic cleanup of subscriptions
- Resource cleanup on client disconnect
- Graceful handling of client failures

## Monitoring and Observability

### Built-in Logging
- Structured logging for message flow
- Debug-level logging for detailed tracing
- Error logging for failure scenarios

### OpenTelemetry Support
- Trace context propagation via `traceparent` field
- Distributed tracing across agent interactions
- Integration with observability platforms

### Metrics (Recommended)
- Message throughput per topic
- Client subscription counts
- Backend performance metrics
- Error rates and types

> See the [Execution](execution.md) section for how messaging integrates with execution engines and [Agents](agents.md) for agent-specific messaging patterns. 