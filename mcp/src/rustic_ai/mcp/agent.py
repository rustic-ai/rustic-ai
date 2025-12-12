import asyncio
import logging
from typing import Dict, List, Optional, Any
import threading
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
from rustic_ai.core.guild import agent
from rustic_ai.core.guild.agent import Agent, ProcessContext, SelfReadyNotification
from rustic_ai.core.guild.agent_ext.mixins.guild_refresher import GuildRefreshMixin

from .models import (
    CallToolRequest,
    CallToolResponse,
    MCPAgentConfig,
    MCPClientType,
    MCPServerConfig,
    ToolResult,
)


class MCPAgent(Agent[MCPAgentConfig], GuildRefreshMixin):
    """
    Agent that connects to MCP servers and exposes their capabilities.
    
    This agent manages MCP client sessions. Due to asyncio event loop constraints,
    sessions must be created and used within the same event loop context.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._session_data: Dict[str, Dict[str, Any]] = {}
        self._server_configs: Dict[str, MCPServerConfig] = {
            s.name: s for s in self.config.servers
        }

    async def _connect_stdio_server(self, config: MCPServerConfig):
        """Connect to a stdio MCP server using AsyncExitStack pattern.
        
        This follows the official MCP documentation pattern to properly manage
        context manager lifecycle.
        """
        self.logger.info(f"Connecting to stdio server: {config.name}")
        
        # Create exit stack for this connection
        exit_stack = AsyncExitStack()
        
        try:
            server_params = StdioServerParameters(
                command=config.command,
                args=config.args,
                env=config.env,
            )
            
            # Enter the stdio_client context using exit stack
            stdio_transport = await exit_stack.enter_async_context(
                stdio_client(server_params)
            )
            read, write = stdio_transport
            
            # Enter the ClientSession context using exit stack
            session = await exit_stack.enter_async_context(
                ClientSession(read, write)
            )
            
            # Initialize the session
            await session.initialize()
            
            # List tools to verify connection
            result = await session.list_tools()
            tool_names = [tool.name for tool in result.tools]
            self.logger.info(f"Connected to {config.name}. Available tools: {tool_names}")
            
            # Store session and exit stack
            with self._lock:
                if config.name not in self._session_data:
                    self._session_data[config.name] = {}
                self._session_data[config.name].update({
                    'session': session,
                    'type': 'stdio',
                    'exit_stack': exit_stack
                })
            
        except Exception as e:
            # Clean up exit stack if connection failed
            await exit_stack.aclose()
            raise e


    async def _connect_sse_server(self, config: MCPServerConfig):
        """Connect to an SSE MCP server using AsyncExitStack pattern.
        
        This follows the official MCP documentation pattern to properly manage
        context manager lifecycle.
        """
        if not config.url:
            raise ValueError(f"URL is required for SSE connection: {config.name}")
        
        self.logger.info(f"Connecting to SSE server: {config.name}")
        
        # Create exit stack for this connection
        exit_stack = AsyncExitStack()
        
        try:
            # Enter the sse_client context using exit stack
            sse_transport = await exit_stack.enter_async_context(
                sse_client(url=config.url, headers=config.headers)
            )
            read, write = sse_transport
            
            # Enter the ClientSession context using exit stack
            session = await exit_stack.enter_async_context(
                ClientSession(read, write)
            )
            
            # Initialize the session
            await session.initialize()
            
            # List tools to verify connection
            result = await session.list_tools()
            tool_names = [tool.name for tool in result.tools]
            self.logger.info(f"Connected to {config.name}. Available tools: {tool_names}")
            
            # Store session and exit stack
            with self._lock:
                if config.name not in self._session_data:
                    self._session_data[config.name] = {}
                self._session_data[config.name].update({
                    'session': session,
                    'type': 'sse',
                    'exit_stack': exit_stack
                })
            
        except Exception as e:
            # Clean up exit stack if connection failed
            await exit_stack.aclose()
            raise e

    # @agent.processor(SelfReadyNotification, handle_essential=True)
    # async def on_ready(self, ctx: ProcessContext[SelfReadyNotification]):
    #     """Connect to configured MCP servers on startup."""
        
    #     for server_config in self.config.servers:
    #         try:
    #             self.logger.info(f"Connecting to MCP server: {server_config.name}")
                
    #             if server_config.type == MCPClientType.STDIO:
    #                 await self._connect_stdio_server(server_config)
    #             elif server_config.type == MCPClientType.SSE:
    #                 await self._connect_sse_server(server_config)
    #             else:
    #                 self.logger.warning(f"Unsupported MCP client type: {server_config.type}")
    #                 continue
                
    #         except Exception as e:
    #             self.logger.error(f"Failed to connect to MCP server {server_config.name}: {e}", exc_info=True)

    async def shutdown(self):
        """Clean up connections on shutdown."""
        self.logger.info("Closing MCP connections...")
        
        with self._lock:
            session_data_copy = dict(self._session_data)
        
        # Close all exit stacks to properly clean up connections
        for name, data in session_data_copy.items():
            exit_stack = data.get('exit_stack')
            if exit_stack:
                try:
                    self.logger.info(f"Closing exit stack for {name}")
                    await exit_stack.aclose()
                    self.logger.info(f"Closed connection to {name}")
                except Exception as e:
                    self.logger.error(f"Error closing connection to {name}: {e}", exc_info=True)
        
        with self._lock:
            self._session_data.clear()

    @agent.processor(CallToolRequest)
    async def handle_tool_call(self, ctx: ProcessContext[CallToolRequest]):
        request = ctx.payload

        for server_config in self.config.servers:
            try:
                self.logger.info(f"Connecting to MCP server: {server_config.name}")
                
                if server_config.type == MCPClientType.STDIO:
                    await self._connect_stdio_server(server_config)
                elif server_config.type == MCPClientType.SSE:
                    await self._connect_sse_server(server_config)
                else:
                    self.logger.warning(f"Unsupported MCP client type: {server_config.type}")
                    continue
                
            except Exception as e:
                self.logger.error(f"Failed to connect to MCP server {server_config.name}: {e}", exc_info=True)
        
        with self._lock:
            session_data = self._session_data.get(request.server_name)

        if not session_data:
            error_msg = f"No connection to MCP server: {request.server_name}"
            self.logger.error(error_msg)
            ctx.send_error(CallToolResponse(results=[], is_error=True))
            return

        session = session_data.get('session')
        if not session:
            error_msg = f"Session not found for MCP server: {request.server_name}"
            self.logger.error(error_msg)
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

            self.logger.info(f"xxx tool_results {tool_results}")

            response = CallToolResponse(results=tool_results)
            ctx.send(response)
            
        except Exception as e:
            self.logger.error(f"Error calling tool {request.tool_name} on {request.server_name}: {e}", exc_info=True)
            ctx.send_error(CallToolResponse(results=[], is_error=True))
