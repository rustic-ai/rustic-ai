"""
Guild Generator Toolset for the ReAct Orchestrator.

This toolset provides tools for building guilds interactively. Tools dispatch
actions to downstream agents (AgentRegistry, RouteBuilder, etc.) via message passing.

The toolset works with GuildGeneratorToolWrapper which extracts pending messages
after each tool execution and sends them via the ProcessContext.
"""

from typing import List, Optional, Union

from pydantic import BaseModel, Field, PrivateAttr

from rustic_ai.core.guild.agent import Agent, ProcessContext
from rustic_ai.core.guild.agent_ext.depends.llm.tools_manager import ToolSpec
from rustic_ai.llm_agent.plugins.base_plugin import BasePlugin
from rustic_ai.llm_agent.plugins.tool_call_wrapper import (
    ToolCallResult,
    ToolCallWrapper,
    ToolSkipResult,
)
from rustic_ai.llm_agent.react.toolset import ReActToolset

from rustic_ai.showcase.guild_generator.models import (
    ActionType,
    AddAgentParams,
    AddRouteParams,
    ExportRequest,
    FlowchartUpdateRequest,
    HelpParams,
    OrchestratorAction,
    PublishParams,
    RemoveAgentParams,
    RemoveRouteParams,
    SetDescriptionParams,
    SetNameParams,
    ShowFlowParams,
    TestFlowParams,
    TestMessage,
)


class GuildGeneratorToolset(ReActToolset):
    """
    Toolset for the Guild Generator ReAct Orchestrator.

    This toolset provides tools for:
    - Adding agents to the guild
    - Adding routes between agents
    - Removing agents and routes
    - Showing the guild flow visualization
    - Testing the guild flow
    - Publishing/exporting the guild spec
    - Setting guild name and description
    - Getting help

    Tools dispatch OrchestratorAction messages to downstream agents, which
    handle the actual processing (e.g., AgentRegistryAgent for add_agent).

    Messages are accumulated in _pending_messages during execute() and then
    extracted by GuildGeneratorToolWrapper.postprocess() to be sent via ctx.
    """

    # Private attribute to accumulate messages during tool execution
    # GuildGeneratorToolWrapper extracts these after each tool call
    _pending_messages: List[BaseModel] = PrivateAttr(default_factory=list)

    def _queue_message(self, payload: BaseModel) -> None:
        """Queue a message to be sent after tool execution."""
        self._pending_messages.append(payload)

    def get_and_clear_pending_messages(self) -> List[BaseModel]:
        """Get all pending messages and clear the queue."""
        messages = self._pending_messages.copy()
        self._pending_messages.clear()
        return messages

    def get_toolspecs(self) -> List[ToolSpec]:
        """Return the list of tool specifications for the Guild Generator."""
        return [
            ToolSpec(
                name="add_agent",
                description=(
                    "Add a new agent to the guild. Describe what the agent should do, "
                    "and optionally provide a hint about the agent type (e.g., 'LLM', "
                    "'splitter', 'aggregator', 'react'). The system will select the "
                    "most appropriate agent type and configure it."
                ),
                parameter_class=AddAgentParams,
            ),
            ToolSpec(
                name="add_route",
                description=(
                    "Add a routing rule to connect agents so messages can flow between them. "
                    "A route has a SOURCE (sender) and TARGET (receiver).\n\n"
                    "Common route patterns:\n"
                    "1. User input route: source='UserProxyAgent', target='YourAgent'\n"
                    "2. Processing route: source='Agent A', target='Agent B'\n"
                    "3. User output route: source='YourAgent', target='user_message_broadcast'\n\n"
                    "Example: To let users send messages to a Text Summarizer:\n"
                    "  add_route(source_agent='UserProxyAgent', target_agent='Text Summarizer')\n\n"
                    "Example: To show agent output to users:\n"
                    "  add_route(source_agent='Text Summarizer', target_agent='user_message_broadcast')\n\n"
                    "Transformation requirements are optional and describe any message format changes needed."
                ),
                parameter_class=AddRouteParams,
            ),
            ToolSpec(
                name="remove_agent",
                description=(
                    "Remove an agent from the guild by name or ID. This also removes "
                    "any routes connected to the agent."
                ),
                parameter_class=RemoveAgentParams,
            ),
            ToolSpec(
                name="remove_route",
                description=(
                    "Remove a routing rule between two agents. Specify the source and "
                    "target agents to identify the route to remove."
                ),
                parameter_class=RemoveRouteParams,
            ),
            ToolSpec(
                name="show_flow",
                description=(
                    "Display the current guild flow as a visual diagram. This shows "
                    "all agents and how they are connected via routes."
                ),
                parameter_class=ShowFlowParams,
            ),
            ToolSpec(
                name="test_flow",
                description=(
                    "Test the guild flow by sending a sample message through it. "
                    "This helps verify that agents and routes are configured correctly."
                ),
                parameter_class=TestFlowParams,
            ),
            ToolSpec(
                name="publish",
                description=(
                    "Export the final guild specification. This validates the guild "
                    "and produces a complete spec that can be used to deploy the guild."
                ),
                parameter_class=PublishParams,
            ),
            ToolSpec(
                name="set_name",
                description="Set or change the name of the guild.",
                parameter_class=SetNameParams,
            ),
            ToolSpec(
                name="set_description",
                description="Set or change the description of the guild.",
                parameter_class=SetDescriptionParams,
            ),
            ToolSpec(
                name="help",
                description=(
                    "Get help on how to use the Guild Generator. Optionally specify "
                    "a topic for more specific help."
                ),
                parameter_class=HelpParams,
            ),
        ]

    def execute(self, tool_name: str, args: BaseModel) -> str:
        """
        Execute a tool by dispatching the appropriate action message.

        Most tools dispatch an OrchestratorAction to downstream agents.
        The actual processing is handled by those agents (AgentRegistryAgent,
        RouteBuilderAgent, StateManagerAgent, etc.).

        Args:
            tool_name: The name of the tool to execute.
            args: The parsed arguments as a Pydantic model instance.

        Returns:
            A confirmation message indicating the action was dispatched.

        Raises:
            ValueError: If the tool name is not recognized.
        """
        if tool_name == "add_agent":
            params = args if isinstance(args, AddAgentParams) else AddAgentParams.model_validate(args)
            self._queue_message(
                OrchestratorAction(
                    action=ActionType.ADD_AGENT,
                    details={
                        "purpose": params.purpose,
                        "agent_type_hint": params.agent_type_hint or "",
                    },
                    user_message=f"Add agent: {params.purpose}",
                )
            )
            return f"Dispatched add_agent action for: {params.purpose}"

        elif tool_name == "add_route":
            params = args if isinstance(args, AddRouteParams) else AddRouteParams.model_validate(args)
            self._queue_message(
                OrchestratorAction(
                    action=ActionType.ADD_ROUTE,
                    details={
                        "source_agent": params.source_agent,
                        "target_agent": params.target_agent,
                        "transformation_requirements": params.transformation_requirements or "",
                    },
                    user_message=f"Add route from {params.source_agent} to {params.target_agent}",
                )
            )
            return f"Dispatched add_route action: {params.source_agent} -> {params.target_agent}"

        elif tool_name == "remove_agent":
            params = args if isinstance(args, RemoveAgentParams) else RemoveAgentParams.model_validate(args)
            self._queue_message(
                OrchestratorAction(
                    action=ActionType.REMOVE_AGENT,
                    details={"agent_name": params.agent_name},
                    user_message=f"Remove agent: {params.agent_name}",
                )
            )
            return f"Dispatched remove_agent action for: {params.agent_name}"

        elif tool_name == "remove_route":
            params = args if isinstance(args, RemoveRouteParams) else RemoveRouteParams.model_validate(args)
            self._queue_message(
                OrchestratorAction(
                    action=ActionType.REMOVE_ROUTE,
                    details={
                        "source_agent": params.source_agent,
                        "target_agent": params.target_agent,
                    },
                    user_message=f"Remove route from {params.source_agent} to {params.target_agent}",
                )
            )
            return f"Dispatched remove_route action: {params.source_agent} -> {params.target_agent}"

        elif tool_name == "show_flow":
            self._queue_message(
                OrchestratorAction(
                    action=ActionType.SHOW_FLOW,
                    details={},
                    user_message="Show flow",
                )
            )
            # Also send a flowchart update request directly
            self._queue_message(FlowchartUpdateRequest(trigger="show_flow"))
            return "Dispatched show_flow action. The guild visualization will be displayed."

        elif tool_name == "test_flow":
            params = args if isinstance(args, TestFlowParams) else TestFlowParams.model_validate(args)
            self._queue_message(
                OrchestratorAction(
                    action=ActionType.TEST_FLOW,
                    details={"test_message": params.test_message},
                    user_message=f"Test flow with: {params.test_message}",
                )
            )
            # Also send the test message
            self._queue_message(TestMessage(content=params.test_message, test_mode=True))
            return f"Dispatched test_flow action with message: {params.test_message}"

        elif tool_name == "publish":
            params = args if isinstance(args, PublishParams) else PublishParams.model_validate(args)
            self._queue_message(
                OrchestratorAction(
                    action=ActionType.PUBLISH,
                    details={
                        "format": params.format,
                        "run_validation": params.run_validation,
                    },
                    user_message="Publish guild",
                )
            )
            # Also send an export request
            self._queue_message(ExportRequest(format=params.format, run_validation=params.run_validation))
            return f"Dispatched publish action. The guild spec will be exported in {params.format} format."

        elif tool_name == "set_name":
            params = args if isinstance(args, SetNameParams) else SetNameParams.model_validate(args)
            self._queue_message(
                OrchestratorAction(
                    action=ActionType.SET_NAME,
                    details={"name": params.name},
                    user_message=f"Set guild name to: {params.name}",
                )
            )
            return f"Dispatched set_name action: {params.name}"

        elif tool_name == "set_description":
            params = args if isinstance(args, SetDescriptionParams) else SetDescriptionParams.model_validate(args)
            self._queue_message(
                OrchestratorAction(
                    action=ActionType.SET_DESCRIPTION,
                    details={"description": params.description},
                    user_message=f"Set guild description",
                )
            )
            return f"Dispatched set_description action"

        elif tool_name == "help":
            params = args if isinstance(args, HelpParams) else HelpParams.model_validate(args)
            self._queue_message(
                OrchestratorAction(
                    action=ActionType.HELP,
                    details={"topic": params.topic or ""},
                    user_message="Help",
                )
            )
            return "Dispatched help action. Help information will be displayed."

        else:
            raise ValueError(f"Unknown tool: {tool_name}")


class GuildGeneratorToolWrapper(ToolCallWrapper):
    """
    Tool wrapper that extracts pending messages from GuildGeneratorToolset
    and sends them via the ProcessContext.

    This wrapper bridges the gap between the synchronous toolset execution
    and the asynchronous message passing required by the guild architecture.

    Usage in guild config:
        "tool_wrappers": [
            {"kind": "rustic_ai.showcase.guild_generator.toolset.GuildGeneratorToolWrapper"}
        ]
    """

    def preprocess(
        self,
        agent: Agent,
        ctx: ProcessContext,
        tool_name: str,
        tool_input: BaseModel,
    ) -> Union[BaseModel, ToolSkipResult]:
        """Pass through the tool input unchanged."""
        return tool_input

    def postprocess(
        self,
        agent: Agent,
        ctx: ProcessContext,
        tool_name: str,
        tool_input: BaseModel,
        tool_output: str,
    ) -> ToolCallResult:
        """
        Extract pending messages from the toolset and return them for sending.

        The ReActAgent will send these messages via ctx after this method returns.
        """
        # Get the toolset from the agent's config
        toolset = getattr(agent.config, "toolset", None)

        messages: List[BaseModel] = []
        if isinstance(toolset, GuildGeneratorToolset):
            messages = toolset.get_and_clear_pending_messages()

        return ToolCallResult(output=tool_output, messages=messages if messages else None)
