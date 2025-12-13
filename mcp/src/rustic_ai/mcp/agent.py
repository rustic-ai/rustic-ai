import asyncio
from typing import Optional, Dict

from rustic_ai.core.guild import agent
from rustic_ai.core.guild.agent import Agent, ProcessContext
from rustic_ai.core.guild.agent_ext.mixins.guild_refresher import GuildRefreshMixin

from .client import MCPClient
from .models import (
    CallToolRequest,
    CallToolResponse,
    MCPAgentConfig,
    MCPServerConfig,
)


class MCPAgent(Agent[MCPAgentConfig], GuildRefreshMixin):
    """
    Agent that connects to a single MCP server and exposes its capabilities.
    """

    def __init__(self):
        self._mcp_client: Optional[MCPClient] = None

    @property
    def server_config(self) -> MCPServerConfig:
        return self.config.server

    def _ensure_client(self):
        if not self._mcp_client:
            self._mcp_client = MCPClient(self.server_config)

    async def initialize(self):
        """Initialize the agent."""
        await super().initialize()
        self._ensure_client()
        # Pre-connect to verify configuration
        if self._mcp_client:
            await self._mcp_client.connect()

    async def shutdown(self):
        """Clean up connection on shutdown."""
        self.logger.info("Closing MCP connection...")
        if self._mcp_client:
            await self._mcp_client.shutdown()

    @agent.processor(CallToolRequest)
    async def handle_tool_call(self, ctx: ProcessContext[CallToolRequest]):
        request = ctx.payload

        # Verify server name matches
        if request.server_name != self.server_config.name:
            self.logger.warning(
                f"Received request for unknown server: {request.server_name}. "
                f"This agent is connected to: {self.server_config.name}"
            )
            ctx.send_error(CallToolResponse(results=[], is_error=True))
            return

        self._ensure_client()
        if not self._mcp_client:
             ctx.send_error(CallToolResponse(results=[], is_error=True))
             return

        response = await self._mcp_client.call_tool(request)
        if response.is_error:
             ctx.send_error(response)
        else:
             ctx.send(response)
