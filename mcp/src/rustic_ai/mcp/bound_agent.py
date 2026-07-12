from typing import Dict, Type

from pydantic import BaseModel, ValidationError

from mcp import ListToolsResult, Tool
from rustic_ai.core.agents.commons.message_formats import ErrorMessage
from rustic_ai.core.guild import agent
from rustic_ai.core.guild.agent import Agent, ProcessContext

from .client import MCPClient
from .models import (
    BoundMCPAgentConfig,
    CallToolRequest,
    ListToolsRequest,
    MCPServerConfig,
)


class BoundMCPAgent(Agent[BoundMCPAgentConfig]):
    """
    MCP agent bound to a fixed, pre-declared allowlist of typed tools.

    Differences from ``MCPAgent``:
    - Skips server-side tool discovery — the allowlist is authoritative.
    - Rejects any ``tool_name`` not in the declared allowlist.
    - Validates ``arguments`` against the user-supplied pydantic schema for
      that tool before any network call.
    """

    def __init__(self):
        self._tool_args: Dict[str, Type[BaseModel]] = {decl.name: decl.parameter_class for decl in self.config.tools}
        self._mcp_client: MCPClient = MCPClient(self.server_config, self.logger)

    @property
    def server_config(self) -> MCPServerConfig:
        return self.config.server

    def _ensure_client(self):
        if not self._mcp_client:
            self._mcp_client = MCPClient(self.server_config, self.logger)

    @agent.processor(CallToolRequest)
    async def handle_tool_call(self, ctx: ProcessContext[CallToolRequest]):
        request = ctx.payload

        args_class = self._tool_args.get(request.tool_name)
        if args_class is None:
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="ToolNotAllowed",
                    error_message=(
                        f"Tool '{request.tool_name}' is not declared on this agent. "
                        f"Allowed tools: {sorted(self._tool_args.keys())}"
                    ),
                )
            )
            return

        try:
            validated = args_class.model_validate(request.arguments, strict=True, extra="forbid")
        except ValidationError as e:
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="InvalidToolArguments",
                    error_message=str(e),
                )
            )
            return

        self._ensure_client()

        forwarded = CallToolRequest(
            tool_name=request.tool_name,
            arguments=validated.model_dump(mode="json"),
        )

        response = await self._mcp_client.call_tool(forwarded)
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
    def handle_list_tools(self, ctx: ProcessContext[ListToolsRequest]):
        tools = [
            Tool(name=t.name, description=t.description, inputSchema=t.parameter_class.model_json_schema())
            for t in self.config.tools
        ]
        ctx.send(ListToolsResult(tools=tools))
