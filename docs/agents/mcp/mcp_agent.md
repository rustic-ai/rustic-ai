# MCPAgent

The `MCPAgent` provides integration with Model Context Protocol (MCP) servers, enabling Rustic AI guilds to leverage external tools and services through a standardized interface.

## Purpose

This agent connects to an MCP server and exposes its tools as callable functions within a guild. It acts as a bridge between Rustic AI's messaging system and MCP's tool protocol, enabling seamless integration with external services.

## Configuration

The `MCPAgent` is configured using `MCPAgentConfig`, which specifies connection details for an MCP server.

### STDIO Configuration (Most Common)

For MCP servers that run as child processes:

```python
{
    "server": {
        "name": "notion",
        "type": "stdio",
        "command": "npx",
        "args": ["-y", "@notionhq/notion-mcp-server"],
        "env": {
            "NOTION_TOKEN": "your_notion_token"
        }
    }
}
```

### SSE Configuration

For remote MCP servers that use Server-Sent Events:

```python
{
    "server": {
        "name": "remote_server",
        "type": "sse",
        "url": "https://example.com/mcp",
        "headers": {
            "Authorization": "Bearer your_token"
        }
    }
}
```

## Message Types

### Input Messages

#### CallToolRequest

A request to call a tool on the MCP server.

```python
class CallToolRequest(BaseModel):
    server_name: str  # Must match the server name in configuration
    tool_name: str    # Name of the tool to call
    arguments: Dict = {}  # Arguments to pass to the tool
```

**Example:**
```python
CallToolRequest(
    server_name="notion",
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
            "name": "notion",
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
    server_name="notion",
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
            "name": "notion",
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
            "name": "playwright",
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
- server_name: "notion" or "playwright"
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

Enable detailed logging to troubleshoot MCP connections:

```python
import logging
logging.getLogger("rustic_ai.mcp").setLevel(logging.DEBUG)
```

## Notes and Limitations

- Each `MCPAgent` connects to exactly one MCP server
- STDIO servers run as child processes and are terminated when the agent shuts down
- SSE servers must be running independently before the agent starts
- Tool schemas are defined by the MCP server, not the agent
- Large responses may impact performance; consider streaming for large data

## Further Reading

- [Personal Workspace Guild Setup](../../howto/personal_workspace_guild_setup.md) - Complete example guild
- [Model Context Protocol Documentation](https://modelcontextprotocol.io/docs)
- [MCP Servers Repository](https://github.com/modelcontextprotocol/servers)
