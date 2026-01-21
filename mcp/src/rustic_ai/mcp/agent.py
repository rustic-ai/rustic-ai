from rustic_ai.core.agents.commons.message_formats import ErrorMessage
from rustic_ai.core.guild import agent
from rustic_ai.core.guild.agent import Agent, ProcessContext

from .client import MCPClient
from .models import (
    CallToolRequest,
    MCPAgentConfig,
    MCPServerConfig,
)


class MCPAgent(Agent[MCPAgentConfig]):
    """
    Agent that connects to a single MCP server and exposes its capabilities.
    """

    def __init__(self):
        self._mcp_client: MCPClient = MCPClient(self.server_config)

    @property
    def server_config(self) -> MCPServerConfig:
        return self.config.server

    def _ensure_client(self):
        if not self._mcp_client:
            self._mcp_client = MCPClient(self.server_config)

    @agent.processor(CallToolRequest)
    async def handle_tool_call(self, ctx: ProcessContext[CallToolRequest]):
        request = ctx.payload

        # Verify server name matches
        if request.server_name != self.server_config.name:
            self.logger.warning(
                f"Received request for unknown server: {request.server_name}. "
                f"This agent is connected to: {self.server_config.name}"
            )
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="UnsupportedMcpServer",
                    error_message=f"Unsupported mcp server {request.server_name}. This agent is connected to: {self.server_config.name}",
                )
            )
            return

        self._ensure_client()
        if not self._mcp_client:
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="MCPClientNotFound",
                    error_message="MCP Client not found!",
                )
            )
            return

        response = await self._mcp_client.call_tool(request)
        if response.is_error:
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="ErrorProcessingMCPRequest",
                    error_message=response.error,
                )
            )
        else:
            ctx.send(response)
