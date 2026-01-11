# Rustic AI Documentation

Welcome to the official documentation for Rustic AI, a powerful framework for building intelligent multi-agent systems in Python. Rustic AI provides a flexible, modular architecture for creating, deploying, and managing AI agents that can work together to solve complex problems.

## What is Rustic AI?

Rustic AI is designed to simplify the development of agent-based systems by providing:

- **Guild-based Architecture**: Organize agents into cohesive groups called "guilds" that work together toward common goals
- **Dependency Injection**: Easily configure and manage the resources your agents need
- **State Management**: Robust mechanisms for handling agent state across interactions
- **Message Passing**: Standardized communication between agents
- **Extensibility**: A plugin-based system that makes it easy to integrate with external services and AI providers

Whether you're building a simple conversational assistant or a complex multi-agent system with specialized roles, Rustic AI provides the infrastructure you need to focus on your application logic rather than agent coordination.

## Getting Started

New to Rustic AI? Here are the best places to begin:

- [Core Concepts](core/index.md): Learn about the foundational architecture and concepts
- [Creating Your First Agent](howto/creating_your_first_agent.md): A step-by-step guide to building your first agent
- [Creating a Guild](howto/creating_a_guild.md): Learn how to organize multiple agents to work together
- [Complete Client-Server Flow](howto/client_server_flow.md): Comprehensive guide for building client applications with proper API integration and real-time communication

## Core Components

Rustic AI is built around these core components:

- [Agents](agents/index.md): The building blocks of intelligent systems that can perceive, reason, and act
- [Guilds](core/guilds.md): Organized collections of agents working together toward common goals
- [Messaging](core/messaging.md): Communication infrastructure for agents to exchange information
  - [Socket Messaging Backend](core/socket_messaging_backend.md): Socket-based messaging for testing without external dependencies
- [Execution](core/execution.md): How agent code gets executed within the Rustic AI framework
  - [Multiprocess Execution](core/multiprocess_execution.md): True parallel execution with process isolation
- [State Management](core/state_management.md): Managing persistence across agent interactions
- [Dependencies](dependencies/index.md): Resources and services that agents can access through dependency injection

## Message Transformation: JSONata and CEL Support

Rustic AI supports both **JSONata** and **CEL (Common Expression Language)** for message and state transformations in routing rules and transformers. Specify the desired type using the `expression_type` field (e.g., `JSONATA` or `CEL`).

**Example:**
```yaml
transformer:
  expression_type: CEL
  style: SIMPLE
  output_format: MyOutputType
  expression: "payload.value > 10 ? 'high' : 'low'"
```

CEL is a fast, safe expression language from Google, suitable for validation, filtering, and transformation logic. JSONata remains supported for advanced JSON querying and transformation.

## Integrations

Rustic AI integrates with popular AI tools and services:

- [LiteLLM](agents/litellm/index.md): Unified interface for various LLM providers
- [HuggingFace](agents/huggingface/index.md): Leverage HuggingFace models for text, image, and speech processing
- [Playwright](agents/playwright/index.md): Web automation and scraping capabilities
- [SerpAPI](agents/serpapi/index.md): Web search integration for information retrieval
- [Marvin](agents/marvin/index.md): AI function calling and structured extraction
- [Ray](ray/index.md): Distributed and parallel execution
- [Chroma](dependencies/chroma/index.md): Vector database for semantic search
- [Redis](dependencies/redis/index.md): Fast key-value storage for agent state
- [LangChain](dependencies/langchain/index.md): Utilities for working with language models

## API Reference

For detailed API information, check out the [API Reference](api/index.md) which provides comprehensive documentation of all public interfaces.

## Showcase

Explore [Example Applications](showcase/index.md) to see Rustic AI in action and get inspiration for your own projects.

## Contributing

Rustic AI is an open-source project, and contributions are welcome! See our [Contributing Guide](contributing.md) to learn how you can help improve the framework. 