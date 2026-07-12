from typing import Optional, Set

from mcp import ListToolsResult
from rustic_ai.core.agents.commons.message_formats import ErrorMessage
from rustic_ai.core.guild import agent
from rustic_ai.core.guild.agent import Agent, ProcessContext

from .client import MCPClient
from .models import (
    CallToolRequest,
    ListToolsRequest,
    MCPAgentConfig,
    MCPServerConfig,
)


class MCPAgent(Agent[MCPAgentConfig]):
    """
    Agent that connects to a single MCP server and exposes its capabilities.

    Discovers the server's tool catalog lazily on the first ``CallToolRequest``
    and caches it for the lifetime of the agent. Subsequent calls are checked
    against the cache and rejected locally if the tool isn't offered.
    """

    def __init__(self):
        self._mcp_client: MCPClient = MCPClient(self.server_config, self.logger)
        self._tools: Optional[Set[str]] = None

    @property
    def server_config(self) -> MCPServerConfig:
        return self.config.server

    def _ensure_client(self):
        if not self._mcp_client:
            self._mcp_client = MCPClient(self.server_config, self.logger)

    @agent.processor(CallToolRequest)
    async def handle_tool_call(self, ctx: ProcessContext[CallToolRequest]):
        request = ctx.payload

        self._ensure_client()

        if self._tools is None:
            try:
                tools = await self._mcp_client.list_tools()
                self._tools = set([tool.name for tool in tools])
            except Exception as e:
                ctx.send_error(
                    ErrorMessage(
                        agent_type=self.get_qualified_class_name(),
                        error_type="ToolDiscoveryFailed",
                        error_message=f"Failed to list tools on the MCP server: {e}",
                    )
                )
                return

        if request.tool_name not in self._tools:
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="ToolNotAllowed",
                    error_message=(
                        f"Tool '{request.tool_name}' is not offered by the MCP server. "
                        f"Available tools: {sorted(self._tools)}"
                    ),
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

    @agent.processor(ListToolsRequest)
    async def handle_list_tools(self, ctx: ProcessContext[ListToolsRequest]):
        try:
            tools = await self._mcp_client.list_tools()
            ctx.send(ListToolsResult(tools=tools))
        except Exception as e:
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="ToolDiscoveryFailed",
                    error_message=f"Failed to list tools on the MCP server: {e}",
                )
            )
