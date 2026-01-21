# Setting Up the Personal Workspace Guild

This guide demonstrates how to build a complete multi-agent system using MCP (Model Context Protocol) integration. The Personal Workspace Guild combines web scraping with Playwright and workspace management with Notion, orchestrated by an intelligent LLM agent.

## Overview

The Personal Workspace Guild is a practical example of how to:

- Integrate multiple MCP servers in a single guild
- Use an LLM agent to orchestrate complex multi-step workflows
- Handle iterative decision-making with context preservation
- Implement proper error handling and validation
- Create a user-friendly assistant for productivity tasks

**What it does:** Users can request web scraping of URLs, and the system automatically extracts content and creates organized Notion pages.

## Architecture

The guild consists of four specialized agents:

1. **Content Moderator**: Screens user input for inappropriate content
2. **Workspace Orchestrator** (LLM): Analyzes requests and determines which services to use
3. **Playwright MCP Agent**: Handles web scraping and browser automation
4. **Notion MCP Agent**: Manages Notion workspace operations

### Message Flow

```
User Request
    ↓
Content Moderator (validates input)
    ↓
Workspace Orchestrator (decides next action)
    ↓
[Playwright Agent OR Notion Agent]
    ↓
Results back to Orchestrator
    ↓
[More actions OR Summary/Done]
    ↓
User receives formatted response
```

## Prerequisites

Before setting up this guild, ensure you have:

- Rustic AI installed with MCP support (`rusticai-mcp` package)
- Node.js and npm installed (for MCP servers)
- A Notion integration token ([create one here](https://www.notion.so/my-integrations))
- Access to Google Vertex AI or another LLM provider

## Step 1: Install MCP Servers

The guild uses two MCP servers that need to be available via npm:

```bash
# These will be automatically downloaded via npx, but you can pre-install them:
npm install -g @notionhq/notion-mcp-server
npm install -g @playwright/mcp@latest
```

## Step 2: Get Your Notion Token

1. Go to [https://www.notion.so/my-integrations](https://www.notion.so/my-integrations)
2. Click "New integration"
3. Give it a name (e.g., "Rustic AI Workspace")
4. Copy the "Internal Integration Token" (starts with `ntn_...`)
5. Share at least one page with your integration in Notion

**Important**: Replace `YOUR_NOTION_TOKEN_HERE` with your actual Notion integration token in the json guild spec.

## Understanding the MCP Integration

### How MCP Agents Work

Each MCP agent:

1. **Spawns an MCP server** as a child process (via `npx` command)
2. **Communicates via STDIO** using the MCP protocol
3. **Translates guild messages** (`CallToolRequest`) into MCP tool calls
4. **Returns results** as `CallToolResponse` messages

### Tool Discovery

To see available tools, check the MCP server documentation:

- **Notion**: [notion-mcp-server docs](https://github.com/notionhq/notion-mcp-server)
- **Playwright**: [playwright-mcp docs](https://github.com/microsoft/playwright-mcp)

## Advanced Customization

### Adding More MCP Servers

You can extend the guild with additional MCP servers:

```json
{
    "id": "github_mcp_agent",
    "name": "GitHub Agent",
    "class_name": "rustic_ai.mcp.agent.MCPAgent",
    "additional_topics": ["GITHUB"],
    "properties": {
        "server": {
            "name": "github",
            "type": "stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-github"],
            "env": {
                "GITHUB_TOKEN": "your_github_token"
            }
        }
    }
}
```

Then update the orchestrator's system prompt to include GitHub tools.

## Resources

- [MCP Agent Documentation](../agents/mcp/mcp_agent.md)
- [Model Context Protocol Spec](https://modelcontextprotocol.io/docs)
- [MCP Servers Repository](https://github.com/modelcontextprotocol/servers)
- [Creating a Guild Guide](creating_a_guild.md)
- [LLM Agent Documentation](../agents/litellm/llm_agent.md)
- [Example Guild Specification](https://github.com/your-repo/demos/blueprints/personal_workspace_guild.json)