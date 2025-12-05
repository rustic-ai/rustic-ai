# Messaging Lifecycle Deep Dive

This guide explains how messages move through Rustic AI, the responsibilities of the messaging layer, and how the Redis backend persists and relays traffic between guild agents. It expands on `docs/core/messaging.md` with a flow-oriented perspective focused on namespacing and guild-aware routing.

## Building Blocks

- **Message (`core/src/rustic_ai/core/messaging/core/message.py`)**: Pydantic record that wraps a `GemstoneID` for globally sortable IDs, tracks topics, payload, priority, routing slips, and message history.
- **MessagingInterface (`core/src/rustic_ai/core/messaging/core/messaging_interface.py`)**: The guild-scoped message bus that registers clients, namespaces topics, persists messages via a pluggable backend, and fans out notifications to subscribers.
- **Clients (`core/src/rustic_ai/core/messaging/client/`)**: Agent-facing adapters (e.g., `MessageTrackingClient`, `ExactlyOnceClient`) that subscribe to topics, buffer delivery, and invoke handler callbacks inside the agent runtime.
- **Backends (`core/src/rustic_ai/core/messaging/backend/` & `redis/src/rustic_ai/redis/messaging/`)**: Storage implementations that honour the `MessagingBackend` contract—Redis is the production choice, while in-memory and embedded variants serve development or tests.

## Namespacing and Guild Mapping

1. **Guild Namespace**: Each guild gets a stable namespace equal to its guild ID (often a slug). The `MessagingInterface` prefixes every topic before reaching the backend, turning `"system"` into `"<guild-id>:system"`. This prevents cross-guild leakage even when sharing a Redis deployment.
2. **Agent Identity**: Agents carry an `AgentTag` (id + name) that is embedded in every `Message.sender`. The tag is also used when a message is forwarded (`ForwardHeader`) or when an agent is explicitly tagged in `recipient_list`.
3. **Topic Patterns**: The guild DSL defines canonical topics such as `GuildTopics.SYSTEM_TOPIC`, agent inboxes (`guild-id:agent_inbox:<agent-id>`), or broadcast channels. Namespacing is transparent to agents—they subscribe to logical names and the interface handles the prefixing.

## Topic Subscription and Client Mapping

- When an agent is launched, `AgentWrapper` registers its client with the `MessagingInterface` and subscribes to the topics declared in the `AgentSpec`.
- The interface maintains a mapping of `namespaced_topic -> set(client_ids)`. Each `client_id` is usually `<guild-id>$<agent-id>` so the interface can differentiate the agent when routing fan-out notifications.
- Clients push incoming `Message` objects into a local priority heap (sorted by `message.id`) before invoking the agent's handler, ensuring in-order processing regardless of backend arrival timing.

## Redis Messaging Backend Flow

1. **Connection Management**: `RedisMessagingBackend` accepts either a live Redis client, a config dict, or a `RedisBackendConfig`. A `RedisConnectionManager` builds a `StrictRedis` or `RedisCluster` instance with keepalive and TLS options.
2. **Publishing**:
   - `MessagingInterface.publish` clones the `Message`, fills `topic_published_to` with the logical topic, and calls `backend.store_message(namespace, namespaced_topic, message_copy)`.
   - `RedisMessageStore.store_message` uses a pipeline to set the JSON payload under `msg:<namespace>:<message-id>` with a TTL (default 3600s) and to `ZADD` the message into the topic's sorted set scored by timestamp. This simultaneously enables random access by id and ordered iteration by time.
   - After persistence succeeds, the store invokes `RedisPubSubManager.publish` to broadcast the payload over Redis pub/sub so subscribers receive the event immediately.
3. **Subscription**:
   - The pub/sub manager maintains a background thread and optional health monitor. It registers one callback per namespaced topic; when Redis delivers a pub/sub message, the manager deserializes the JSON into a `Message` and forwards it to the `MessagingInterface` callback.
   - The interface then looks up subscribed clients (excluding cases where the sender is the same client and the topic is a self-inbox) and calls `client.notify_new_message(message)` for each.
4. **History Retrieval**: API calls such as `get_messages_for_topic_since` translate a message id into a timestamp (via `GemstoneID`) and run `ZRANGEBYSCORE` to fetch persisted entries. The same mechanism powers history enrichment when `Message.enrich_with_history` is set.

## End-to-End Example

1. **Agent Publish**: The `ProbeAgent` in `core/tests/guild/test_guild_message.py` generates a `Message` via its injected client (`MessageTrackingClient`) and calls `publish_dict`. The client hands it to `MessagingInterface.publish`.
2. **Namespace & Persist**: The interface prefixes the broadcast topic (`user_broadcast`) with the guild id, stores it through the Redis backend, and publishes it over pub/sub.
3. **Fan-out**: The pub/sub manager emits the message to the interface, which forwards it to every subscribed user proxy agent except the originator. Each agent's client receives the `Message`, pushes it on its heap, and the agent handler consumes it.
4. **Forwarding & History**: If an agent forwards the message, `ForwardHeader` records the original id and on-behalf-of tag. Downstream processors can reconstruct the journey because `message_history` accumulates `ProcessEntry` items at every hop.

## Operational Considerations

- **Exactly-once Consumption**: `ExactlyOnceClient` persists the last delivered id in a `LastProcessedMsg` SQL table. On restart it resumes by calling `MessagingInterface.get_next_message_for_client`. Redis retains the backlog because every publish is stored in a sorted set until TTL expiry.
- **Backpressure & Ordering**: Using `GemstoneID` ensures message IDs increase monotonically with timestamp and priority. Clients rely on the id ordering when multiple topics converge into a single agent inbox.
- **Scaling Guilds**: Multiple guilds can share one Redis cluster thanks to namespacing. Sharding by namespace is straightforward—deploy a Redis instance per region and point `MessagingConfig` to the appropriate endpoint.
- **TTL Tuning**: Adjust `RUSTIC_AI_REDIS_MSG_TTL` to control how long historical messages remain queryable. Long TTLs favour debugging and replay, while shorter TTLs reduce memory usage.

Use this document alongside `docs/core/messaging.md` and `docs/core/embedded_messaging_backend.md` when you need a mental model of how message objects, guild-aware namespaces, and the Redis backend cooperate to move information between agents.
