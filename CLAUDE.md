# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Rustic AI is a modular, multi-agent AI framework built around a "guild" architecture where agents collaborate on long-running tasks. The repository is a Poetry monorepo containing multiple packages that extend the core framework with integrations for LLMs, vector databases, web automation, and distributed execution.

## Build & Development Commands

### Setup
```bash
# Install Poetry plugin for monorepo support
poetry self add poetry-plugin-mono-repo-deps@0.3.2

# Install all dependencies including dev tools
poetry install --with dev --all-extras
```

### Testing
```bash
# Run all tests across all modules (requires Redis)
docker compose -f scripts/redis/docker-compose.yml up
poetry run tox

# Run tests for a specific file
poetry run pytest core/tests/utils/test_gemstone_id.py

# Test a new module individually before integration
cd <module-name>
poetry install --with dev --all-extras
poetry shell
tox
```

**Environment variables required for integration tests:**
- `OPENAI_API_KEY`
- `HUGGINGFACE_API_KEY`
- `SERP_API_KEY`

### Code Quality
```bash
# Format code
poetry run tox -e format
# Or directly:
isort .
black .

# Lint code
poetry run tox -e lint
# Or directly:
flake8
mypy .
```

### Building
```bash
# Build all modules
./scripts/poetry_install.sh
./scripts/poetry_build.sh

# Build Docker image (Linux)
docker build -t rusticai-api .

# Build Docker image (macOS)
docker buildx build --platform linux/amd64 -t rusticai-api .
```

## Architecture

### Core Concepts

**Guilds** (`core/src/rustic_ai/core/guild/guild.py`): Collections of agents that share a messaging bus, execution engine, and state. Each guild has a unique ID that namespaces all topics and prevents cross-guild message leakage.

**Agents** (`core/src/rustic_ai/core/guild/agent.py`): Task-specific AI workers that process messages via decorated handler methods. Agents are defined declaratively using `AgentSpec` and launched within guilds. Each agent subscribes to topics and uses `@processor` decorators to handle incoming messages.

**Messaging System** (`core/src/rustic_ai/core/messaging/`): Guild-scoped pub/sub message bus with pluggable backends (Redis for production, in-memory for testing). Messages use `GemstoneID` for globally sortable identifiers and maintain full routing history. Topics are automatically namespaced per guild (e.g., `"system"` becomes `"<guild-id>:system"`).

**Dependency Injection** (`core/src/rustic_ai/core/guild/agent_ext/depends/`): Agents declare dependencies via `DependencySpec` in their spec or via `AgentDependency` strings in `@processor` decorators. Dependencies can be scoped at agent level or guild level. Common dependencies include LLMs, databases, filesystems, and knowledge bases.

**Execution Engines** (`core/src/rustic_ai/core/guild/execution/`): Manage agent lifecycle and runtime. `SyncExecutionEngine` runs agents in threads, while `RayExecutionEngine` (`ray/`) enables distributed execution across clusters.

### Message Flow

1. Agent calls `context.send(payload)` in a processor method
2. `ProcessContext` resolves routing via `RoutingSlip` rules from guild spec
3. Message is persisted to backend (Redis sorted set scored by timestamp)
4. Backend publishes notification via pub/sub
5. `MessagingInterface` fans out to subscribed clients (excluding sender for self-inbox)
6. Clients push messages into priority heap sorted by `GemstoneID`
7. Target agent's processor is invoked with `ProcessContext`

Each message carries:
- `message_history`: List of `ProcessEntry` tracking agent hops
- `routing_slip`: Optional `RoutingSlip` defining multi-step workflows
- `session_state`: Dict for context passing between processors
- `thread`: List of message IDs forming a conversation chain

### Module Organization

The repository follows a consistent structure per module:
```
<module-name>/
  src/rustic_ai/<module-name>/     # Source code
  tests/                            # Tests using pytest
  pyproject.toml                    # Poetry config with dependencies
  tox.ini                           # Test automation config
  README.md                         # Module documentation
```

**Core modules:**
- `core/`: Base abstractions (Agent, Guild, Messaging, State)
- `redis/`: Redis messaging backend and state management
- `ray/`: Distributed execution engine
- `api/`: FastAPI server for guild management
- `testing/`: Test utilities (`wrap_agent_for_testing`, probe agents)

**LLM integrations:**
- `litellm/`: Unified LLM interface supporting 100+ providers
- `marvin/`: Marvin AI integration
- `llm-agent/`: Pluggable LLM agent with tool calling
- `huggingface/`: HuggingFace models (diffusion, TTS, etc.)
- `vertexai/`: Google Vertex AI integration

**Data & tools:**
- `chroma/`: Chroma vector database integration
- `lancedb/`: LanceDB vector database integration
- `langchain/`: LangChain integration
- `serpapi/`: SerpAPI search integration
- `playwright/`: Web automation agents

**Other:**
- `showcase/`: Example guilds and demos
- `cookiecutter-rustic/`: Template for creating new modules

## Agent Development Patterns

### Creating an Agent

Use `AgentBuilder` for programmatic construction:

```python
from rustic_ai.core.guild.builders import AgentBuilder
from rustic_ai.core.guild.dsl import DependencySpec

agent_spec = (
    AgentBuilder(MyAgent)
    .set_name("MyAgent")
    .set_description("Description")
    .set_dependency_map({
        "llm": DependencySpec(
            class_name="rustic_ai.litellm.agent_ext.llm.LiteLLMResolver",
            properties={"model": "gpt-4"}
        )
    })
    .build_spec()
)
```

Agent class with message handlers:

```python
from rustic_ai.core.guild.agent import Agent, processor, ProcessContext
from pydantic import BaseModel

class MyRequest(BaseModel):
    query: str

class MyAgent(Agent):
    @processor(clz=MyRequest, depends_on=["llm"])
    def handle_request(self, ctx: ProcessContext[MyRequest], llm):
        response = llm.generate(ctx.payload.query)
        ctx.send(MyResponse(result=response))
```

### Dependency Injection

**In AgentSpec (guild/agent level):**
```python
dependency_map={
    "logger": DependencySpec(
        class_name="my_package.resolvers.LoggerResolver",
        properties={"log_level": "DEBUG"}
    )
}
```

**In processor method:**
```python
@processor(clz=MyMessage, depends_on=["llm", "db:guild"])
def handle(self, ctx: ProcessContext[MyMessage], llm, db):
    # llm is agent-scoped, db is guild-scoped
    pass
```

Dependency string format: `"<key>"` (agent-scoped) or `"<key>:guild"` (guild-scoped)

### Testing Agents

Use `wrap_agent_for_testing` from `testing/`:

```python
from rustic_ai.testing import wrap_agent_for_testing

async def test_my_agent():
    harness = wrap_agent_for_testing(
        agent_spec=my_agent_spec,
        guild_spec=guild_spec,
    )

    harness.send_message(MyRequest(query="test"))

    messages = harness.get_sent_messages()
    assert len(messages) == 1
    assert isinstance(messages[0].payload, MyResponse)
```

Test utilities support:
- Dependency mocking via overridden resolvers
- Probe agents for message inspection
- Message flow assertions
- Isolation from Redis (uses embedded backend)

## Repository Conventions

**Python version:** 3.12 (strict requirement)

**Line length:** 120 characters (configured in `pyproject.toml`)

**Import order (isort):**
1. Third-party packages
2. `rustic_ai` first-party packages
3. Local module imports

**Commit messages:** Follow [Conventional Commits](https://www.conventionalcommits.org/) (e.g., `feat:`, `fix:`, `docs:`)

**Adding dependencies:**
- NEVER add dependencies to root `pyproject.toml` (only submodules allowed there)
- Add to relevant submodule's `pyproject.toml`
- After updating a dependency in one module, update dependents:
  ```bash
  ./scripts/run_on_each.sh poetry update rusticai-<module>
  poetry update rusticai-*
  ```

**Creating new modules:**
```bash
poetry shell
cookiecutter cookiecutter-rustic/
```

## Configuration

**Global config:** `conf/` directory contains YAML/`.conf` files for system-wide settings

**Module config:** Each module has its own `pyproject.toml` for dependencies and settings

**Environment variables:** Integrations use env vars for API keys:
- `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` (LLMs)
- `HUGGINGFACE_API_KEY` (HuggingFace)
- `SERP_API_KEY` (SerpAPI)
- `VERTEXAI_PROJECT` (Vertex AI)
- `RUSTIC_AI_REDIS_MSG_TTL` (Redis message TTL in seconds, default 3600)

**Redis configuration:** Redis is required for distributed guilds. Launch via:
```bash
docker compose -f scripts/redis/docker-compose.yml up
```
Access Redis Insight at http://localhost:5540/ (host: `redis`, port: `6379`)

## Key Implementation Details

**GemstoneID** (`core/src/rustic_ai/core/utils/gemstone_id.py`): Snowflake-style IDs combining timestamp (41 bits), machine ID (10 bits), priority (3 bits), and sequence (10 bits). Provides globally unique, sortable identifiers.

**Message processors** use `@processor` decorator with:
- `clz`: Message type (BaseModel class) to handle
- `predicate`: Optional filter function for conditional processing
- `handle_essential`: Whether to process messages on essential topics (state, errors)
- `depends_on`: List of dependency keys to inject

**ProcessContext** (`core/src/rustic_ai/core/guild/agent.py`): Passed to every processor method, provides:
- `ctx.payload`: Parsed message payload
- `ctx.send(payload)`: Send response message
- `ctx.send_error(payload)`: Send error message
- `ctx.message`: Original message with metadata
- `ctx.agent`: Reference to agent instance
- `ctx.update_context(dict)`: Update session state for downstream processors

**AgentFixtures** for lifecycle hooks:
- `@AgentFixtures.before_process`: Called before every processor
- `@AgentFixtures.after_process`: Called after every processor
- `@AgentFixtures.on_send`: Called when sending messages
- `@AgentFixtures.on_send_error`: Called when sending error messages
- `@AgentFixtures.outgoing_message_modifier`: Modify outgoing messages

**GuildBuilder** (`core/src/rustic_ai/core/guild/builders.py`): Fluent API for guild construction with execution engine selection, messaging config, and agent registration.

## Common Pitfalls

- Don't forget to start Redis before running integration tests
- Agent classes need `@processor` decorators for message handling (plain methods are ignored)
- Dependencies must be registered in `dependency_map` before use
- Guild namespacing prevents agents in different guilds from seeing each other's messages
- Message TTL in Redis affects history replay—tune `RUSTIC_AI_REDIS_MSG_TTL` for your use case
- When testing agents, use `wrap_agent_for_testing` to avoid Redis dependency
- Module structure must follow the pattern (src/, tests/, pyproject.toml, README.md)
