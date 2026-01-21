import asyncio
import logging
from typing import Optional

import httpx

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


def _extract_error_message(exc: Exception) -> str:
    """Extract a meaningful error message from an exception."""
    # Check for HTTPStatusError in exception chain or ExceptionGroup
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code} {exc.response.reason_phrase} for {exc.request.url}"

    return str(exc)


class MCPClient:
    """
    Client for connecting to an MCP server and executing tools.
    Manages the session in a background task to satisfy anyio/asyncio constraints.
    """

    def __init__(self, config: MCPServerConfig):
        self.config = config
        self._session: Optional[ClientSession] = None
        self._task: Optional[asyncio.Task] = None
        # Lazy-initialized asyncio primitives (created in the correct event loop when first accessed)
        self._shutdown_event: Optional[asyncio.Event] = None
        self._ready_event: Optional[asyncio.Event] = None
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None
        self._last_error: Optional[str] = None

    def _ensure_events(self):
        """
        Ensures that asyncio Event objects are created in the current event loop.
        Recreates them if the event loop has changed since they were last created.
        """
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            # No event loop running, cannot create events yet
            return

        # If events don't exist or were created in a different loop, recreate them
        if self._event_loop is None or self._event_loop != current_loop:
            self._shutdown_event = asyncio.Event()
            self._ready_event = asyncio.Event()
            self._event_loop = current_loop
            logger.debug(f"Created asyncio Events for MCP client {self.config.name} in event loop {id(current_loop)}")

    @property
    def shutdown_event(self) -> asyncio.Event:
        """Lazy property for shutdown event."""
        self._ensure_events()
        return self._shutdown_event  # type: ignore[return-value]

    @property
    def ready_event(self) -> asyncio.Event:
        """Lazy property for ready event."""
        self._ensure_events()
        return self._ready_event  # type: ignore[return-value]

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
                    self.ready_event.set()

                    # Wait until shutdown is requested
                    await self.shutdown_event.wait()

        except Exception as e:
            if not self.shutdown_event.is_set():
                detailed_error = _extract_error_message(e)
                error_msg = f"MCP session error for {self.config.name}: {detailed_error}"
                self._last_error = error_msg
                logger.error(error_msg, exc_info=True)
        finally:
            self._session = None
            if self._ready_event:  # Only clear if event was created
                self._ready_event.clear()

    async def connect(self) -> Optional[ClientSession]:
        """Ensures connection to the server exists."""
        if self._session:
            return self._session

        if not self._task or self._task.done():
            # Ensure events are created in the current event loop
            self._ensure_events()
            self.shutdown_event.clear()
            self._last_error = None  # Clear previous errors
            self._task = asyncio.create_task(self._run_session())

        # Wait for session to be ready
        try:
            await asyncio.wait_for(self.ready_event.wait(), timeout=10.0)
        except asyncio.TimeoutError:
            error_detail = f" Last error: {self._last_error}" if self._last_error else ""
            logger.error(f"Timeout waiting for MCP connection to {self.config.name}.{error_detail}")
            # Cleanup if timeout
            self.shutdown_event.set()
            if self._task:
                try:
                    await self._task
                except Exception:
                    pass
            return None

        return self._session

    async def call_tool(self, request: CallToolRequest) -> CallToolResponse:
        session = await self.connect()

        if not session:
            error_msg = "mcp session not found!"
            if self._last_error:
                error_msg += f" Reason: {self._last_error}"
            return CallToolResponse(results=[], is_error=True, error=error_msg)

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
            return CallToolResponse(
                results=[], is_error=True, error=f"Error calling tool {request.tool_name} on {self.config.name}: {e}"
            )
