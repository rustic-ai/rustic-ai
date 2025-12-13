import asyncio
import logging
from typing import Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client

from .models import (
    CallToolRequest,
    CallToolResponse,
    MCPClientType,
    MCPServerConfig,
    ToolResult,
)

logger = logging.getLogger(__name__)


class MCPClient:
    """
    Client for connecting to an MCP server and executing tools.
    Manages the session in a background task to satisfy anyio/asyncio constraints.
    """

    def __init__(self, config: MCPServerConfig):
        self.config = config
        self._session: Optional[ClientSession] = None
        self._task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        self._ready_event = asyncio.Event()

    async def _run_session(self):
        """Background task to maintain the session."""
        try:
            transport_context = None
            if self.config.type == MCPClientType.STDIO:
                server_params = StdioServerParameters(
                    command=self.config.command,
                    args=self.config.args,
                    env=self.config.env,
                )
                transport_context = stdio_client(server_params)
            elif self.config.type == MCPClientType.SSE:
                if not self.config.url:
                    raise ValueError(f"URL is required for SSE connection: {self.config.name}")
                transport_context = sse_client(url=self.config.url, headers=self.config.headers)
            else:
                logger.warning(f"Unsupported MCP client type: {self.config.type}")
                return

            client_type = self.config.type

            async with transport_context as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()

                    # Verify connection by listing tools
                    result = await session.list_tools()
                    tool_names = [tool.name for tool in result.tools]
                    logger.info(f"Connected to {self.config.name} ({client_type.value}). Available tools: {tool_names}")

                    self._session = session
                    self._ready_event.set()

                    # Wait until shutdown is requested
                    await self._shutdown_event.wait()

        except Exception as e:
            if not self._shutdown_event.is_set():
                logger.error(f"MCP session error for {self.config.name}: {e}", exc_info=True)
        finally:
            self._session = None
            self._ready_event.clear()

    async def connect(self) -> Optional[ClientSession]:
        """Ensures connection to the server exists."""
        if self._session:
            return self._session

        if not self._task or self._task.done():
            self._shutdown_event.clear()
            self._task = asyncio.create_task(self._run_session())

        # Wait for session to be ready
        try:
            await asyncio.wait_for(self._ready_event.wait(), timeout=10.0)
        except asyncio.TimeoutError:
            logger.error(f"Timeout waiting for MCP connection to {self.config.name}")
            # Cleanup if timeout
            self._shutdown_event.set()
            if self._task:
                try:
                    await self._task
                except Exception:
                    pass
            return None

        return self._session

    async def shutdown(self):
        """Clean up connection on shutdown."""
        logger.info(f"Closing MCP connection to {self.config.name}...")
        self._shutdown_event.set()
        if self._task:
            try:
                await self._task
            except Exception as e:
                logger.error(f"Error awaiting MCP task shutdown: {e}", exc_info=True)
            self._task = None

    async def call_tool(self, request: CallToolRequest) -> CallToolResponse:
        session = await self.connect()

        if not session:
            return CallToolResponse(results=[], is_error=True)

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

            return CallToolResponse(results=tool_results)

        except Exception as e:
            logger.error(
                f"Error calling tool {request.tool_name} on {self.config.name}: {e}",
                exc_info=True,
            )
            return CallToolResponse(results=[], is_error=True)
