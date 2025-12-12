from enum import Enum
from typing import Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field
from rustic_ai.core.guild.dsl import BaseAgentProps


class MCPClientType(str, Enum):
    STDIO = "stdio"
    SSE = "sse"


class MCPServerConfig(BaseModel):
    name: str = Field(description="Name of the MCP server")
    type: MCPClientType = Field(default=MCPClientType.STDIO, description="Type of connection")
    
    # Stdio config
    command: Optional[str] = Field(None, description="Command to execute for stdio")
    args: List[str] = Field(default_factory=list, description="Arguments for the command")
    env: Dict[str, str] = Field(default_factory=dict, description="Environment variables")
    
    # SSE config
    url: Optional[str] = Field(None, description="URL for SSE connection")
    headers: Dict[str, str] = Field(default_factory=dict, description="Headers for SSE connection")


class MCPAgentConfig(BaseAgentProps):
    servers: List[MCPServerConfig] = Field(default_factory=list, description="List of MCP servers to connect to")


class CallToolRequest(BaseModel):
    server_name: str
    tool_name: str
    arguments: Dict = Field(default_factory=dict)


class ToolResult(BaseModel):
    type: Literal["text", "image", "resource"]
    content: Union[str, Dict] 


class CallToolResponse(BaseModel):
    results: List[ToolResult]
    is_error: bool = False
