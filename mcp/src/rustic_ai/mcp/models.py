from enum import Enum
from typing import Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, HttpUrl, model_validator

from rustic_ai.core.guild.agent_ext.depends.llm.tools_manager import BaseToolDeclaration
from rustic_ai.core.guild.dsl import BaseAgentProps


class MCPClientType(str, Enum):
    STDIO = "stdio"
    HTTP = "http"


class MCPServerConfig(BaseModel):
    type: MCPClientType = Field(default=MCPClientType.STDIO, description="Type of connection")

    # Stdio config
    command: Optional[str] = Field(None, description="Command to execute for stdio")
    args: List[str] = Field(default_factory=list, description="Arguments for the command")
    env: Dict[str, str] = Field(default_factory=dict, description="Environment variables")

    # HTTP config
    url: Optional[HttpUrl] = Field(None, description="URL for HTTP connection")
    headers: Dict[str, str] = Field(default_factory=dict, description="Additional Non-Authorization headers")
    auth_header: Optional[str] = Field("Authorization", description="Authorization header")

    @model_validator(mode="after")
    def _require_transport_fields(self) -> "MCPServerConfig":
        if self.type == MCPClientType.STDIO and not self.command:
            raise ValueError("'command' is required when type is STDIO")
        if self.type == MCPClientType.HTTP and not self.url:
            raise ValueError("'url' is required when type is HTTP")
        return self


class MCPAgentConfig(BaseAgentProps):
    server: MCPServerConfig = Field(description="MCP server configuration")


class CallToolRequest(BaseModel):
    tool_name: str
    arguments: Dict = Field(default_factory=dict)


class ToolResult(BaseModel):
    type: Literal["text", "image", "resource"]
    content: Union[str, Dict]


class CallToolResponse(BaseModel):
    results: List[ToolResult]
    is_error: bool = False
    error: Optional[str] = None


class MCPToolDeclaration(BaseToolDeclaration):
    # Keep this class empty for now; we may want to support additional fields like output_format, etc. in the future.
    pass


class BoundMCPAgentConfig(BaseAgentProps):
    """
    Config for ``BoundMCPAgent``: one MCP server plus a non-empty, deduplicated
    list of tool declarations forming the agent's allowlist.
    """

    server: MCPServerConfig = Field(description="MCP server configuration")
    tools: List[MCPToolDeclaration] = Field(min_length=1, description="Declared tool allowlist")


class ListToolsRequest(BaseModel):
    """Request to list tools.

    Attributes:
        command: Command to execute (e.g., 'list_tools').
    """

    command: str = "list_tools"
