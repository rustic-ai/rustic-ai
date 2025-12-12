import asyncio
from dataclasses import dataclass
from typing import Dict, Optional
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
from rustic_ai.core.guild import agent
from rustic_ai.core.guild.agent import Agent, ProcessContext
from rustic_ai.core.guild.agent_ext.mixins.guild_refresher import GuildRefreshMixin

from .models import (
    CallToolRequest,
    CallToolResponse,
    MCPAgentConfig,
    MCPClientType,
    MCPServerConfig,
    ToolResult,
)


@dataclass
class MCPSessionContext:
    session: ClientSession
    exit_stack: AsyncExitStack
    client_type: str


class MCPAgent(Agent[MCPAgentConfig], GuildRefreshMixin):
    """
    Agent that connects to MCP servers and exposes their capabilities.
    
    This agent manages MCP client sessions. Due to asyncio event loop constraints,
    sessions must be created and used within the same event loop context.
    """

    def __init__(self):
        self._sessions: Dict[str, MCPSessionContext] = {}
        self._connection_locks: Dict[str, asyncio.Lock] = {}

    @property
    def server_configs(self) -> Dict[str, MCPServerConfig]:
        return {s.name: s for s in self.config.servers}

    async def _initialize_session(
        self, 
        transport_context, 
        config: MCPServerConfig, 
        client_type: str
    ) -> MCPSessionContext:
        """Helper to initialize session from a transport context."""
        exit_stack = AsyncExitStack()
        try:
            # Enter the transport context
            read, write = await exit_stack.enter_async_context(transport_context)
            
            # Enter the ClientSession context
            session = await exit_stack.enter_async_context(
                ClientSession(read, write)
            )
            
            # Initialize the session
            await session.initialize()
            
            # Verify connection by listing tools
            result = await session.list_tools()
            tool_names = [tool.name for tool in result.tools]
            self.logger.info(f"Connected to {config.name} ({client_type}). Available tools: {tool_names}")
            
            return MCPSessionContext(
                session=session,
                exit_stack=exit_stack,
                client_type=client_type
            )
            
        except Exception as e:
            await exit_stack.aclose()
            raise e

    async def _connect_server(self, server_name: str) -> Optional[ClientSession]:
        """Ensures connection to the specified server exists."""
        
        # Fast path check
        if server_name in self._sessions:
            return self._sessions[server_name].session

        config = self.server_configs.get(server_name)
        if not config:
            self.logger.error(f"Server configuration not found for: {server_name}")
            return None

        # Lock for this specific server to prevent race conditions
        if server_name not in self._connection_locks:
            self._connection_locks[server_name] = asyncio.Lock()

        async with self._connection_locks[server_name]:
            # Double check inside lock
            if server_name in self._sessions:
                return self._sessions[server_name].session

            self.logger.info(f"Connecting to MCP server: {server_name}")
            try:
                if config.type == MCPClientType.STDIO:
                    server_params = StdioServerParameters(
                        command=config.command,
                        args=config.args,
                        env=config.env,
                    )
                    session_ctx = await self._initialize_session(
                        stdio_client(server_params), 
                        config, 
                        'stdio'
                    )
                elif config.type == MCPClientType.SSE:
                    if not config.url:
                        raise ValueError(f"URL is required for SSE connection: {server_name}")
                    session_ctx = await self._initialize_session(
                        sse_client(url=config.url, headers=config.headers),
                        config,
                        'sse'
                    )
                else:
                    self.logger.warning(f"Unsupported MCP client type: {config.type}")
                    return None

                self._sessions[server_name] = session_ctx
                return session_ctx.session

            except Exception as e:
                self.logger.error(f"Failed to connect to MCP server {server_name}: {e}", exc_info=True)
                return None

    async def shutdown(self):
        """Clean up connections on shutdown."""
        self.logger.info("Closing MCP connections...")
        
        # Copy items to avoid modification during iteration
        sessions = list(self._sessions.values())
        self._sessions.clear()
        
        for ctx in sessions:
            try:
                await ctx.exit_stack.aclose()
            except Exception as e:
                self.logger.error(f"Error closing MCP connection: {e}", exc_info=True)

    @agent.processor(CallToolRequest)
    async def handle_tool_call(self, ctx: ProcessContext[CallToolRequest]):
        request = ctx.payload
        
        session = await self._connect_server(request.server_name)
        
        if not session:
            # Error logging is handled in _connect_server or specific cases
            ctx.send_error(CallToolResponse(results=[], is_error=True))
            return

        try:
            result = await session.call_tool(request.tool_name, arguments=request.arguments)
            
            tool_results = []
            for content in result.content:
                 if content.type == "text":
                     tool_results.append(ToolResult(type="text", content=content.text))
                 elif content.type == "image":
                     tool_results.append(ToolResult(type="image", content=content.data))
                 elif content.type == "resource":
                     tool_results.append(ToolResult(type="resource", content=content.resource.uri))

            response = CallToolResponse(results=tool_results)
            ctx.send(response)
            
        except Exception as e:
            self.logger.error(f"Error calling tool {request.tool_name} on {request.server_name}: {e}", exc_info=True)
            ctx.send_error(CallToolResponse(results=[], is_error=True))
