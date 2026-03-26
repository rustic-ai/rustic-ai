"""
Models for the Guild Generator.

These define the message types exchanged between agents in the guild generator.
"""

from enum import StrEnum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, JsonValue

from rustic_ai.core.guild import AgentSpec
from rustic_ai.core.messaging.core.message import RoutingRule


class ActionType(StrEnum):
    """Types of actions the orchestrator can take."""

    ADD_AGENT = "add_agent"
    ADD_ROUTE = "add_route"
    REMOVE_AGENT = "remove_agent"
    REMOVE_ROUTE = "remove_route"
    TEST_FLOW = "test_flow"
    SHOW_FLOW = "show_flow"
    PUBLISH = "publish"
    HELP = "help"
    SET_NAME = "set_name"
    SET_DESCRIPTION = "set_description"


class OrchestratorAction(BaseModel):
    """
    Action command from the orchestrator agent.

    The orchestrator interprets user intent and produces this action
    to be processed by the appropriate downstream agent.
    """

    action: ActionType
    details: Dict[str, Any] = Field(default_factory=dict)
    user_message: str = ""


class AgentRegistryInfo(BaseModel):
    """Information about an available agent type."""

    class_name: str
    name: str
    description: str
    input_formats: List[str] = Field(default_factory=list)
    output_formats: List[str] = Field(default_factory=list)
    required_dependencies: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    example_properties: Dict[str, Any] = Field(default_factory=dict)


class AgentLookupRequest(BaseModel):
    """Request to find an appropriate agent type."""

    description: str  # What the user wants the agent to do
    input_format: Optional[str] = None  # Expected input message format
    output_format: Optional[str] = None  # Expected output message format


class AgentLookupResponse(BaseModel):
    """Response with suggested agent specification."""

    agent_spec: Dict[str, Any]  # AgentSpec as dict for JSON serialization
    explanation: str  # Why this agent was chosen
    available_agents: List[AgentRegistryInfo] = Field(default_factory=list)
    input_formats: List[str] = Field(default_factory=list)  # Message types this agent accepts
    output_formats: List[str] = Field(default_factory=list)  # Message types this agent sends


class TransformationSpec(BaseModel):
    """Specification for a message transformation."""

    style: str = "simple"  # "simple" or "content_based_router"
    expression_type: str = "jsonata"
    handler: str  # The JSONata expression
    output_format: Optional[str] = None


class TransformRequest(BaseModel):
    """Request to create a transformation between message types."""

    source_format: str
    target_format: str
    source_agent_name: str
    target_agent_name: str
    requirements: str = ""  # Additional requirements for the transformation


class TransformResponse(BaseModel):
    """Response with the generated transformation."""

    transformation: TransformationSpec
    explanation: str


class RouteRequest(BaseModel):
    """Request to create a routing rule."""

    agent_name: str
    agent_id: Optional[str] = None
    agent_type: Optional[str] = None
    method_name: Optional[str] = None
    message_format: str
    destination_topic: Optional[str] = None
    transformation: Optional[TransformationSpec] = None
    route_times: int = -1  # -1 means route every time


class RouteResponse(BaseModel):
    """Response with the created routing rule."""

    routing_rule: Dict[str, Any]  # RoutingRule as dict for JSON serialization
    explanation: str


class AgentMessageInfo(BaseModel):
    """Message type information for an agent in the guild."""

    agent_id: str
    agent_name: str
    class_name: str
    input_formats: List[str] = Field(default_factory=list)
    output_formats: List[str] = Field(default_factory=list)


class GuildBuilderState(BaseModel):
    """
    State of the guild being built.

    This is stored in guild_state.guild_builder.
    """

    name: str = "New Guild"
    description: str = "A guild created with Guild Generator"
    agents: List[Dict[str, Any]] = Field(default_factory=list)  # List of AgentSpec dicts
    routes: List[Dict[str, Any]] = Field(default_factory=list)  # List of RoutingRule dicts
    agent_message_info: List[AgentMessageInfo] = Field(default_factory=list)  # Message type info for each agent


class FlowchartUpdateRequest(BaseModel):
    """Request to update the flowchart visualization."""

    trigger: str = "update"


class ExportRequest(BaseModel):
    """Request to export the guild spec."""

    format: str = "json"
    run_validation: bool = True


class ExportResponse(BaseModel):
    """Response with the exported guild spec."""

    guild_spec: Dict[str, Any]
    is_valid: bool
    validation_errors: List[str] = Field(default_factory=list)
    json_output: str = ""


class TestMessage(BaseModel):
    """
    Message for testing the guild flow.

    When the user sends a message without tagging @Orchestrator,
    it gets wrapped in this and routed through the dynamic router.
    """

    content: str
    test_mode: bool = True


class VisualizationResponse(BaseModel):
    """Response containing a VegaLite visualization spec."""

    response: dict[str, JsonValue]
    explanation: str
