# Enterprise Integration Patterns in Rustic AI

This document explains how to implement various Enterprise Integration Patterns (EIPs) using the routing system in Rustic AI. The routing system is built on the concept of a **Routing Slip**, which is a list of processing steps that a router should follow.

## Core Multi-Agent System EIPs

The following patterns are fundamental to Rustic AI's multi-agent architecture and directly support agent collaboration, communication, and coordination.

### Message Bus

The Rustic AI messaging system itself acts as a Message Bus. It provides a common infrastructure for agents to communicate with each other without having to know about each other's specific locations or implementations.

### Publish-Subscribe Channel

A Publish-Subscribe Channel allows multiple subscribers to receive the same message. This is the default messaging model in Rustic AI. When a message is published to a topic, all agents subscribed to that topic will receive a copy of the message. 

### Point-to-Point Channel

A Point-to-Point Channel, where a message is delivered to only one specific agent, is achieved by sending the message to that agent's inbox. Every agent has a unique **agent_inbox** that only it subscribes to. The topic for the agent's inbox is `agent_inbox:{agent_id}`.

**Demos**
- [Point to Point Guild in Python](./001_point_to_point.ipynb)
- Point to Point Guild from YAML
    - [YAML Spec](./001_point_to_point.yaml)
    - [Notebook](./001_point_to_point_yaml.ipynb)

### Message Router

A Message Router consumes a message from one channel and republishes it to a different channel based on a set of conditions. This is essential for orchestrating multi-agent workflows.

#### Origin Based Routing

In this case the router decides the destination based on certain origin parameters. 

Origin based routing allows filtering using:

- origin_sender
- origin_topic
- origin_message_format

**Demos**
- [Origin based routing Guild in Python](./002_basic_message_routing.ipynb)
- Origin based routing Guild from YAML
    - [YAML Spec](./002_basic_message_routing.yaml)
    - [Notebook](./002_basic_message_routing_yaml.ipynb)

### Content-Based Router

A Content-Based Router is a specific type of message router that routes messages based on their content. This is implemented using a `RoutingRule` with a `FunctionalTransformer`. A functional transformer applies a [JSONata](https://jsonata.org/) expression to the MessageRoutable. The JSONata transformation should return a MessageRoutable with new routes.

The Message is routed based on the partial `MessageRoutable` returned from JSONata expression, combining it with default values.

These are the fields in MessageRoutable:

- **topics** (Union[str, List[str]]): The topics to which the message should be published.
- **recipient_list** (List[AgentTag]): List of agents tagged in the message.
- **payload** (JsonDict): The actual content or payload of the message.
- **format** (str): The type of the message.
- **forward_header** (Optional[ForwardHeader]): The header for a forwarded message.
- **context** (Optional[JsonDict]): The context of the message.
- **enrich_with_history** (Optional[int]): The number of previous messages to include in the context.

**Demos**

- [Content Based Routing Guild in Python](./003_content_based_router.ipynb)
- Content Based Routing Guild from YAML
    - [YAML Spec](./003_content_based_router.yaml)
    - [Notebook](./003_content_based_router_yaml.ipynb)

### Message Filter

A Message Filter is a component that eliminates unwanted messages from a flow. This can be achieved in Rustic AI by adding a runtime predicate (JSONata) to agent spec. The SimpleRuntimePredicate gets to filter incoming messages based on message content, agent state and guild state.

The runtime predicate can be used to filter messages before the agent sees them. The filter can be applied on:
- **message**: The dictionary for complete incoming message
- **agent_state**: The dictionary for the current agent state
- **guild_state**: The dictionary for the current guild state

**Demos**
- [Message filter with RuntimePredicate in Python](./004_message_filter.ipynb)
- Message filter with RuntimePredicate from YAML
    - [YAML Spec](./004_message_filter.yaml)
    - [Notebook](./004_message_filter_yaml.ipynb)

### Message Translator

A Message Translator converts a message from one format to another. This is crucial for enabling agents with different message formats to communicate effectively. Rustic AI provides two powerful approaches for implementing message translation, each suited for different use cases.

#### PayloadTransformer Approach

The `PayloadTransformer` is used when you only need to transform the message payload while keeping the routing information unchanged. This approach is ideal for simple format conversions between message types.

**Use Case Example:** Converting customer service requests into internal ticket format
- **Input:** `CustomerRequest` (customer-facing format)
- **Output:** `InternalTicket` (internal system format)
- **Transformation:** Maps priority levels, generates ticket IDs, restructures customer information

**Demos**

- [Message Translator with PayloadTransformer in Python](./005_message_translator_payload.ipynb)
- Message Translator with PayloadTransformer from YAML
    - [YAML Spec](./005_message_translator_payload.yaml)
    - [Notebook](./005_message_translator_payload_yaml.ipynb)

#### FunctionalTransformer Approach

The `FunctionalTransformer` provides complete control over the entire `MessageRoutable`, allowing you to transform both the payload and routing information. This approach enables dynamic routing based on transformed content.

**Use Case Example:** Converting e-commerce orders into inventory checks with priority-based routing
- **Input:** `OrderRequest` (order information)
- **Output:** `InventoryCheck` (inventory validation request)
- **Dynamic Routing:** High-value orders → `inventory_high_priority`, Low-value orders → `inventory_normal`
- **Business Logic:** Calculates order totals, determines priority levels, routes accordingly

**Demos**
- [Message Translator with FunctionalTransformer in Python](./005_message_translator_functional.ipynb)
- Message Translator with FunctionalTransformer from YAML
    - [YAML Spec](./005_message_translator_functional.yaml)
    - [Notebook](./005_message_translator_functional_yaml.ipynb)

### Scatter-Gather

The Scatter-Gather pattern involves broadcasting a message to multiple recipients and then aggregating their responses. This is essential for coordinating multiple agents to work on parts of a problem and combining their results.

**Use Case Example**
- **Input:** `AnalysisRequest` to start an analysis with the data
- **Process:** The message is scattered for statistical analysis, trend analysis and anomaly analysis
- **Output:** Aggregated Comprehensive Report from the the Reporting agent

**Demos**
- [Scatter Gather in Pyhton](./006_scatter_gather.ipynb)
- Scatter Gather from YAML
    - [YAML Spec](./006_scatter_gather.yaml)
    - [Notebook](./006_scatter_gather_yaml.ipynb)

_Additional Info:_
- [Message Models](./helpers/scatter_gather_models.py)
- [Domain Agents](./helpers/scatter_gather_agents.py)


### Recipient List

A Recipient List is a component that routes a message to a list of statically defined recipients. This enables coordinated multi-agent workflows where specific sets of agents need to process the same message.

#### TBD

### Dynamic Router

A Dynamic Router routes messages to different channels based on conditions that can be determined only at runtime. This enables adaptive multi-agent systems that can change their behavior based on current state, load, or other runtime conditions.

#### TBD

### Aggregator

An Aggregator collects and stores individual messages until a complete set of related messages has been received. This is essential for implementing multi-agent workflows where results from multiple agents need to be combined.

#### TBD

### Splitter

A Splitter breaks a composite message into a series of individual messages. This enables distributing work across multiple agents by breaking down complex tasks into smaller, manageable parts.

#### TBD

### Resequencer

A Resequencer reorders messages so that they can be processed in a specific order. This is important for multi-agent workflows where the order of processing matters for correctness.

#### TBD

### Routing Slip

A Routing Slip defines a sequence of processing steps that a message should follow. Rustic AI's routing system is built on this concept, where each route defines the next step in message processing across multiple agents.

#### TBD

### Process Manager

A Process Manager maintains the state of a multi-step business process and coordinates the message flow between process steps. This is crucial for orchestrating complex multi-agent workflows that span multiple interactions.

#### TBD

### Load Balancer

A Load Balancer distributes messages across multiple instances of the same agent type to ensure optimal resource utilization. This is important for scaling multi-agent systems under high load.

#### TBD

### Message Endpoint

A Message Endpoint connects an application to a messaging channel. In Rustic AI, agents act as message endpoints, providing the interface between the application logic and the messaging infrastructure.

#### TBD

### Dead Letter Queue

A Dead Letter Queue handles messages that cannot be processed successfully. Rustic AI provides a built-in dead letter queue mechanism for handling failed message processing, which is crucial for robust multi-agent systems.

#### TBD

### Wiretap

A Wiretap inspects messages that travel through a channel without affecting the message flow. This is useful for monitoring and debugging multi-agent interactions without disrupting the workflow.

#### TBD

### Content Enricher

A Content Enricher adds missing information to a message by consulting external data sources. This enables agents to augment messages with additional context needed by downstream agents.

#### TBD

### Content Filter

A Content Filter removes unimportant data items from a message, leaving only the essential information. This helps optimize message processing in multi-agent systems by reducing unnecessary data transfer.

#### TBD

### Detour

A Detour routes a message through intermediate steps for debugging, testing, or monitoring purposes before sending it to its actual destination. This is useful for testing and debugging multi-agent workflows.

#### TBD


## System Infrastructure EIPs

The following patterns relate to system-level infrastructure and management, which may be relevant for production deployments but are less central to multi-agent collaboration.

### Message Bridge

A Message Bridge connects two otherwise independent messaging systems. In Rustic AI, this could be implemented as an agent that receives messages from one guild and forwards them to another guild or external system.

#### TBD

### Control Bus

A Control Bus is a special channel that allows the messaging system to be monitored and managed. This can be implemented using special administrative topics and agents that handle system management commands.

#### TBD

### Message Store

A Message Store provides reliable message storage and retrieval capabilities. This can be implemented using persistent storage backends integrated with Rustic AI agents.

#### TBD

### Smart Proxy

A Smart Proxy tracks messages sent to a channel and their responses, providing additional services like request-response correlation, timeout handling, and response caching.

#### TBD

### Test Message

A Test Message is a special message used to test the messaging system without affecting business logic. This can be implemented using special message types that are handled by test-specific agents.

#### TBD

### Channel Purger

A Channel Purger removes messages from a channel based on certain criteria such as age, content, or system state. This can be implemented as a maintenance agent that periodically cleans up message queues.

#### TBD

### Message Broker

A Message Broker decouples the destination of a message from the sender and maintains central control over the flow of messages. The Rustic AI messaging infrastructure acts as a message broker.

#### TBD

### Message History

Message History tracks all messages that have passed through a system for audit, debugging, or replay purposes. This can be implemented using message logging agents.

#### TBD

### Message Journal

A Message Journal provides a persistent record of all messages for compliance, audit, or recovery purposes. This extends beyond Message History to provide guaranteed persistence.

#### TBD

### Service Activator

A Service Activator connects a service to the messaging system, allowing the service to be invoked through messaging. In Rustic AI, agents can act as service activators by wrapping external services.

#### TBD

### Invalid Message Channel

An Invalid Message Channel handles messages that are malformed or cannot be processed. This works in conjunction with the Dead Letter Queue to handle different types of message failures.

#### TBD

### Retry

A Retry mechanism attempts to reprocess failed messages after a delay. This can be implemented using agent state management and delayed message republishing.

#### TBD

## Not Applicable to Multi-Agent Systems

The following patterns are either not relevant to Rustic AI's multi-agent architecture or are better handled by other system components outside the messaging framework.

### Envelope Wrapper

An Envelope Wrapper encapsulates a message with additional metadata required by the messaging infrastructure while keeping the original message intact. In Rustic AI, this is handled by the core messaging system and is not something agents typically need to implement.

#### Not Applicable - Handled by Core System

### Claim Check

A Claim Check stores large message payloads in a separate storage system and replaces them with a reference token. This is more of a system-level optimization and not specific to multi-agent coordination patterns.

#### Not Applicable - System-Level Optimization

### Normalizer

A Normalizer converts messages from different sources into a common format. While useful, this is typically handled by Message Translators and is not a distinct pattern in the context of agent collaboration.

#### Not Applicable - Covered by Message Translator

### Canonical Data Model

A Canonical Data Model defines a common data format used by all applications in an integration solution. This is a design principle rather than an implementation pattern and is enforced through Pydantic models in Rustic AI.

#### Not Applicable - Design Principle

### Composed Message Processor

A Composed Message Processor processes a composite message. This is the default behavior of all agents in Rustic AI and doesn't represent a special pattern.

#### Not Applicable - Default Agent Behavior

### Event Sourcing Integration

Event Sourcing captures all changes to application state as a sequence of events. While potentially useful, this is an application-level pattern that agents may implement internally, not a messaging pattern.

#### Not Applicable - Application Pattern

### CQRS Integration

Command Query Responsibility Segregation (CQRS) separates read and write operations. This is an architectural pattern that may influence agent design but is not a messaging integration pattern.

#### Not Applicable - Architectural Pattern

### Circuit Breaker

A Circuit Breaker prevents cascading failures by temporarily blocking calls to a failing service. This is a resilience pattern that may be implemented within agents but is not a messaging pattern.

#### Not Applicable - Resilience Pattern

### Bulkhead

A Bulkhead isolates critical resources to prevent failures from cascading across the system. This is a system architecture pattern, not a messaging integration pattern.

#### Not Applicable - System Architecture Pattern
