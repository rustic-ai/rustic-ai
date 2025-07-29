# Enterprise Integration Patterns in Rustic AI

This document explains how to implement various Enterprise Integration Patterns (EIPs) using the routing system in Rustic AI. The routing system is built on the concept of a **Routing Slip**, which is a list of processing steps that a router should follow.

## Messaging EIPs

The following sections describe how to implement various messaging EIPs in Rustic AI.

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

A Message Router consumes a message from one channel and republishes it to a different channel based on a set of conditions. 

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

A Content-Based Router is a specific type of message router that routes messages based on their content. This is implemented using a `RoutingRule` with a `FunctionalTransformer`. A functional transformer applies a [JSONata](https://jsonata.org/) expression to the MessageRoutable. Thee JSONata transformation should return a MessageRoutable with new routes.

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

The runtime predicate can be used to filter messages before the agent sees them. The filter cann be applied on -
- **message**: The dictionary for complete incoming message
- **agent_state**: The dictionary for the  current agent state
- **guild_state**: The dictionary for the current guild state

**Demos**
- [Message filter with RuntimePredicate in Python](./004_message_filter.ipynb)
- Message filter with RuntimePredicate from YAML
    - [YAML Spec](./004_message_filter.yaml)
    - [Notebook](./004_message_filter_yaml.ipynb)


### Message Translator

A Message Translator converts a message from one format to another. This can be implemented using a `PayloadTransformer` or `FunctionalTransformer` in a `RoutingRule`.

#### TBD


### Splitter

A Splitter breaks a composite message into a series of individual messages. This can be implemented in an agent's processor method by iterating over the composite message and sending a new message for each part.

#### TBD


### Aggregator

An Aggregator collects and stores individual messages until a complete set of related messages has been received. This can be implemented by creating a stateful agent that stores the messages it receives until a certain condition is met.

#### TBD


### Resequencer

A Resequencer reorders messages so that they can be processed in a specific order. This can be implemented by creating a stateful agent that buffers messages and reorders them based on a sequence number in the message.

#### TBD


### Composed Message Processor

A Composed Message Processor is a component that processes a composite message. This is the default behavior of agents in Rustic AI. An agent's processor method receives the entire message and can process it as a whole.

#### TBD


### Scatter-Gather

The Scatter-Gather pattern involves broadcasting a message to multiple recipients and then aggregating their responses. This can be implemented by using a combination of a Recipient List and an Aggregator.


#### TBD


### MORE TO COME
