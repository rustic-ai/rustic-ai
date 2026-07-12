# MCP Agents

The `mcp` package provides two agents for integrating with Model Context Protocol (MCP) servers:

- **`MCPAgent`** — discovers tools dynamically from the server. Use for prototyping and exploration.
- **`BoundMCPAgent`** — restricted to a pre-declared, typed allowlist of tools. **Recommended for production.**

Both agents bridge Rustic AI's messaging system to MCP's tool protocol, enabling seamless integration with external services.

## Choosing Between MCPAgent and BoundMCPAgent

| Concern | `MCPAgent` | `BoundMCPAgent` |
|---|---|---|
| Tool surface | Whatever the server currently advertises | Fixed, explicit allowlist |
| Tool discovery | Lazy `list_tools` call on first request | None — declarations are authoritative |
| Argument validation | None — forwarded as-is | Validated against a pydantic schema (`strict=True`, `extra="forbid"`) before any network call |
| Drift safety | A server-side tool change is invisible until it fails at runtime | A server-side breaking change is caught at validation, not after the call |
| Best for | Iterating on a new server, ad-hoc tool calls | Production workloads with a known, audited set of tools |

Prefer `BoundMCPAgent` once you know which tools you actually need — the allowlist gives you a clear contract, fails fast on bad arguments, and prevents callers from invoking tools you didn't sign up for.

## Purpose

These agents connect to an MCP server and expose its tools as callable functions within a guild. They act as a bridge between Rustic AI's messaging system and MCP's tool protocol, enabling seamless integration with external services.

## Configuration

The `MCPAgent` is configured using `MCPAgentConfig`, which specifies connection details for an MCP server.

### STDIO Configuration

For MCP servers that run as child processes:

```python
{
    "server": {
        "type": "stdio",
        "command": "npx",
        "args": ["-y", "@notionhq/notion-mcp-server"],
        "env": {
            "NOTION_TOKEN": "your_notion_token"
        }
    }
}
```

### HTTP Configuration

For remote MCP servers that speak the Streamable HTTP transport:

```python
{
    "server": {
        "type": "http",
        "url": "https://example.com/mcp"
    }
}
```

If the remote server requires bearer auth, set the `MCP_TOKEN` environment
variable on the process running the agent. The client will send it as
`Authorization: Bearer <MCP_TOKEN>` on every request.

## Message Types

### Input Messages

#### CallToolRequest

A request to call a tool on the MCP server.

```python
class CallToolRequest(BaseModel):
    tool_name: str    # Name of the tool to call
    arguments: Dict = {}  # Arguments to pass to the tool
```

**Example:**
```python
CallToolRequest(
    tool_name="API-post-page",
    arguments={
        "parent": {"page_id": "abc-123"},
        "properties": {
            "title": {
                "title": [{"text": {"content": "My Page"}}]
            }
        }
    }
)
```

### Output Messages

#### CallToolResponse

Sent when a tool call completes successfully:

```python
class CallToolResponse(BaseModel):
    results: List[ToolResult]  # Results from the tool
    is_error: bool = False     # Whether an error occurred
    error: Optional[str] = None  # Error message if is_error is True
```

Each `ToolResult` contains:
- `type`: "text", "image", or "resource"
- `content`: The actual result data (string or dict)

#### ErrorMessage

Sent when a tool call fails:

```python
class ErrorMessage(BaseModel):
    agent_type: str      # Class name of the agent
    error_type: str      # Type of error that occurred
    error_message: str   # Detailed error message
```

Common error types:
- `UnsupportedMcpServer`: Request sent to wrong server
- `MCPClientNotFound`: MCP client initialization failed
- `ErrorProcessingMCPRequest`: Tool execution failed

## Behavior

1. **Initialization**: The agent spawns or connects to the MCP server based on configuration
2. **Request Processing**: When a `CallToolRequest` is received:
   - Validates that the server name matches
   - Calls the specified tool with the provided arguments
   - Returns results via `CallToolResponse` or errors via `ErrorMessage`
3. **Shutdown**: Cleanly disconnects from the MCP server when the agent stops

## Sample Usage

### Basic Agent Setup

```python
from rustic_ai.core.guild.builders import AgentBuilder
from rustic_ai.mcp.agent import MCPAgent

# Configure the Notion MCP agent
notion_agent_spec = {
    "id": "notion_mcp_agent",
    "name": "Notion Agent",
    "description": "Handles Notion operations via MCP",
    "class_name": "rustic_ai.mcp.agent.MCPAgent",
    "properties": {
        "server": {
            "type": "stdio",
            "command": "npx",
            "args": ["-y", "@notionhq/notion-mcp-server"],
            "env": {
                "NOTION_TOKEN": "your_notion_integration_token"
            }
        }
    }
}

# Add to guild
guild_builder.add_agent_spec(notion_agent_spec)
```

### Calling MCP Tools

```python
from rustic_ai.mcp.models import CallToolRequest

# Create a tool call request
request = CallToolRequest(
    tool_name="API-post-search",
    arguments={"query": "my workspace"}
)

# Send to the MCP agent
client.publish("default_topic", request)
```

### Multiple MCP Servers

You can run multiple MCP agents in the same guild, each connecting to a different server:

```python
# Notion agent for workspace management
notion_agent = {
    "id": "notion_agent",
    "class_name": "rustic_ai.mcp.agent.MCPAgent",
    "properties": {
        "server": {
            "type": "stdio",
            "command": "npx",
            "args": ["-y", "@notionhq/notion-mcp-server"],
            "env": {"NOTION_TOKEN": "token1"}
        }
    }
}

# Playwright agent for web scraping
playwright_agent = {
    "id": "playwright_agent",
    "class_name": "rustic_ai.mcp.agent.MCPAgent",
    "properties": {
        "server": {
            "type": "stdio",
            "command": "npx",
            "args": ["-y", "@playwright/mcp@latest"],
            "env": {}
        }
    }
}

guild_builder.add_agent_spec(notion_agent)
guild_builder.add_agent_spec(playwright_agent)
```

## BoundMCPAgent

`BoundMCPAgent` is configured with an explicit list of tool declarations. Each declaration pairs a tool name with a pydantic `BaseModel` class that defines the tool's argument schema. The agent:

1. Rejects any `tool_name` not in the declared allowlist (`ToolNotAllowed`).
2. Validates `arguments` against the declared pydantic schema with `strict=True, extra="forbid"` before any network call (`InvalidToolArguments`).
3. Forwards the validated, model-dumped arguments to the MCP server.

Server-side `list_tools` is never called — the local declarations are the contract.

### Configuration

`BoundMCPAgentConfig` extends the MCP server config with a non-empty list of `MCPToolDeclaration` entries:

```python
{
    "server": {
        "type": "http",
        "url": "https://api.godaddy.com/v1/domains/mcp"
    },
    "tools": [
        {
            "name": "domains_suggest",
            "parameter_class": "rustic_ai.mcp.connectors.godaddy.DomainsSuggestInput"
        },
        {
            "name": "domains_check_availability",
            "parameter_class": "rustic_ai.mcp.connectors.godaddy.DomainsCheckAvailabilityInput"
        }
    ]
}
```

Each `MCPToolDeclaration` has:
- `name`: tool name as exposed by the MCP server
- `parameter_class`: either a pydantic ``BaseModel`` subclass or its fully-qualified class name defining the argument schema. Resolution is validated at config-load time, so misspellings or non-`BaseModel` classes fail immediately.
- `description`: optional human/LLM-facing description

### Pre-generated Connector Schemas

`rustic_ai.mcp.connectors` ships pydantic input models generated from known MCP providers (e.g. `godaddy`, `google-maps`, `google-calendar`, `atlassian-rovo`, `datacommons`, `peek`, `alltrails`). Each connector module's docstring includes a ready-to-paste `BoundMCPAgentConfig` for that provider.

To regenerate or add a new connector, see `mcp/scripts/generate_mcp_models.py`, which reads a YAML list of providers, fetches each server's tool schemas, and emits pydantic models via `datamodel-code-generator`.

### Sample Usage

```python
from rustic_ai.core.guild.builders import AgentBuilder
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.mcp.bound_agent import BoundMCPAgent
from rustic_ai.mcp.connectors.godaddy import (
    DomainsCheckAvailabilityInput,
    DomainsSuggestInput,
)
from rustic_ai.mcp.models import (
    BoundMCPAgentConfig,
    MCPClientType,
    MCPServerConfig,
    MCPToolDeclaration,
)

config = BoundMCPAgentConfig(
    server=MCPServerConfig(
        type=MCPClientType.HTTP,
        url="https://api.godaddy.com/v1/domains/mcp",
    ),
    tools=[
        MCPToolDeclaration(
            name="domains_suggest",
            parameter_class=DomainsSuggestInput,
        ),
        MCPToolDeclaration(
            name="domains_check_availability",
            parameter_class=get_qualified_class_name(DomainsCheckAvailabilityInput),
        ),
    ],
)

godaddy_agent_spec = (
    AgentBuilder(BoundMCPAgent)
    .set_id("godaddy_mcp_agent")
    .set_name("GoDaddy MCP Agent")
    .set_description("Domain suggestions and availability via GoDaddy MCP")
    .set_properties(config)
    .build_spec()
)

guild_builder.add_agent_spec(godaddy_agent_spec)
```

Callers send the same `CallToolRequest` message type as for `MCPAgent`; the contract on the wire is unchanged.

### Additional Error Types

In addition to the errors documented under [Error Handling](#error-handling), `BoundMCPAgent` emits:

- `ToolNotAllowed`: the request's `tool_name` is not in the declared allowlist. The error message enumerates the allowed tools so the caller can recover.
- `InvalidToolArguments`: the supplied `arguments` failed pydantic validation against the tool's `parameter_class` schema (missing required field, wrong type, or unknown field).

## Orchestrating MCP Tools

For complex workflows involving multiple MCP servers, use an LLM agent as an orchestrator:

```python
# LLM orchestrator that decides which MCP server to use
orchestrator_spec = {
    "id": "orchestrator",
    "class_name": "rustic_ai.llm_agent.llm_agent.LLMAgent",
    "properties": {
        "model": "vertex_ai/gemini-3-pro-preview",
        "default_system_prompt": """
You analyze user requests and determine which MCP service to call.
Return JSON with:
- target: "notion" or "playwright" (used to route to the right MCP agent's topic)
- tool_name: the specific tool to call
- arguments: tool parameters
"""
    }
}
```

See the [Personal Workspace Guild Setup](../../howto/personal_workspace_guild_setup.md) guide for a complete example.

## Available Tools

The available tools depend on the MCP server you connect to. To discover tools:

1. Check the server's documentation
2. Use MCP inspector tools
3. Call the server's list_tools endpoint (if supported)


## Environment Variables

MCP servers often require API keys or configuration via environment variables. Set these in the `env` field of the server configuration:

```python
"env": {
    "NOTION_TOKEN": "secret_...",
    "API_KEY": "your_key",
    "DATABASE_URL": "postgresql://..."
}
```

## Error Handling

The agent provides detailed error messages:

```python
# Server name mismatch
ErrorMessage(
    agent_type="rustic_ai.mcp.agent.MCPAgent",
    error_type="UnsupportedMcpServer",
    error_message="Unsupported mcp server playwright. This agent is connected to: notion"
)

# Tool execution failure
CallToolResponse(
    results=[],
    is_error=True,
    error="Tool 'invalid_tool' not found on server 'notion'"
)
```

## Best Practices

1. **Server Naming**: Use descriptive server names that match the service (e.g., "notion", "github", "playwright")
2. **Error Recovery**: Handle `ErrorMessage` responses in your orchestrator or downstream agents
3. **Environment Security**: Use secrets management for API tokens, don't hardcode them
4. **Connection Management**: The agent automatically manages server connections and reconnection
5. **Tool Discovery**: Document available tools for your specific MCP servers
6. **Testing**: Test MCP integrations individually before adding to complex guilds

## Advanced Configuration

### Custom MCP Servers

You can build custom MCP servers using the MCP SDK and connect them via the MCPAgent:

```python
{
    "server": {
        "name": "custom_server",
        "type": "stdio",
        "command": "python",
        "args": ["/path/to/your/mcp_server.py"],
        "env": {}
    }
}
```

### Debugging

The `MCPClient` logs through the owning agent's logger, so MCP connection
output appears under the per-agent logger name
(`Agent[<agent-name>:<agent-id>]`) rather than `rustic_ai.mcp`. To enable
detailed logging for a specific agent:

```python
import logging
logging.getLogger("Agent[Notion Agent:notion_mcp_agent]").setLevel(logging.DEBUG)
```

To enable debug logging for every agent in the process, raise the root
logger level instead:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Notes and Limitations

- Each agent instance connects to exactly one MCP server
- STDIO servers run as child processes and are terminated when the agent shuts down
- HTTP (Streamable HTTP) servers must be running independently before the agent starts
- For `MCPAgent`, tool schemas are defined by the MCP server, not the agent
- For `BoundMCPAgent`, the declared pydantic schema is the local contract — if the server changes its schema, regenerate the connector models (see `mcp/scripts/generate_mcp_models.py`) and update the agent's config
- Large responses may impact performance; consider streaming for large data

## Further Reading

- [Personal Workspace Guild Setup](../../howto/personal_workspace_guild_setup.md) - Complete example guild
- [Model Context Protocol Documentation](https://modelcontextprotocol.io/docs)
- [MCP Servers Repository](https://github.com/modelcontextprotocol/servers)
