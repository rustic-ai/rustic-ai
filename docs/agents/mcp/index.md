# MCP Agents

This section contains documentation for Rustic AI's Model Context Protocol (MCP) integration, which enables agents to connect to and interact with MCP servers.

## Available Agents

- [MCPAgent](mcp_agent.md) - Connect to MCP servers and expose their tools as agent capabilities

## Overview

The Model Context Protocol (MCP) is an open standard that enables seamless integration between LLM applications and external data sources and tools. Rustic AI's MCP agent allows you to incorporate any MCP server into your agent system, enabling access to a wide range of external services through a standardized interface.

MCP agents act as bridges between Rustic AI's guild system and MCP servers, translating guild messages into MCP tool calls and returning results back to the guild.

## What is MCP?

The Model Context Protocol standardizes how AI applications connect to data sources. MCP servers expose:

- **Tools**: Functions that can be called by agents
- **Resources**: Data and content that can be accessed
- **Prompts**: Templated messages for LLM interactions

Learn more at [modelcontextprotocol.io](https://modelcontextprotocol.io)

## Use Cases

- **Integration with external services**: Connect to Notion, GitHub, Slack, and other services via MCP servers
- **Web automation**: Use Playwright MCP server for browser automation
- **Database access**: Query databases through MCP servers
- **Custom tools**: Build and expose your own tools via MCP
- **Multi-tool workflows**: Orchestrate multiple MCP servers in a single guild

## Supported Connection Types

The MCP agent supports two connection methods:

1. **STDIO**: Spawn MCP servers as child processes (most common)
2. **SSE**: Connect to remote MCP servers via Server-Sent Events

## Available MCP Servers

Popular MCP servers you can use include:

- **@notionhq/notion-mcp-server**: Notion workspace integration
- **@playwright/mcp**: Browser automation with Playwright
- **@modelcontextprotocol/server-filesystem**: Local filesystem access
- **@modelcontextprotocol/server-github**: GitHub API integration
- **@modelcontextprotocol/server-postgres**: PostgreSQL database queries

See the [MCP Servers Directory](https://github.com/modelcontextprotocol/servers) for more options.

## Getting Started

To use MCP agents, you need:

1. An MCP server (installed via npm or available via URL)
2. Configuration for connecting to the server
3. Proper agent setup in your guild specification

Refer to the [MCPAgent](mcp_agent.md) documentation for detailed implementation instructions and the [Personal Workspace Guild Setup](../../howto/personal_workspace_guild_setup.md) guide for a complete working example.

## Example Guild with MCP

See the [Personal Workspace Guild](../../howto/personal_workspace_guild_setup.md) for a complete example that combines:
- Notion MCP server for page creation
- Playwright MCP server for web scraping
- LLM orchestrator for coordinating multi-step workflows
