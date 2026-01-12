"""
Tool call wrapper plugin for ReActAgent.

This module provides the ToolCallWrapper base class that allows plugins to:
- Modify tool inputs before execution
- Skip tool execution (e.g., return cached results)
- Modify tool outputs after execution
- Handle errors with custom logic
- Generate additional messages
"""

from abc import abstractmethod
from typing import List, Optional, Union

from pydantic import BaseModel

from rustic_ai.core.guild.agent import Agent, ProcessContext
from rustic_ai.llm_agent.plugins.base_plugin import BasePlugin


class ToolSkipResult(BaseModel):
    """
    Return this from preprocess() to skip tool execution.

    When a ToolCallWrapper's preprocess method returns this instead of the
    tool input, the actual tool execution is skipped and this output is used
    directly (e.g., for caching).

    Example:
        def preprocess(self, agent, ctx, tool_name, tool_input):
            cached = self.cache.get(tool_name, tool_input)
            if cached:
                return ToolSkipResult(output=cached)
            return tool_input
    """

    output: str
    """The output to use instead of executing the tool."""


class ToolCallResult(BaseModel):
    """
    Result from postprocess() containing the output and optional messages.

    This is returned from postprocess() to allow both modifying the output
    and generating additional messages.
    """

    output: str
    """The (possibly modified) tool output."""

    messages: Optional[List[BaseModel]] = None
    """Optional messages to emit from this tool call."""


class ToolCallWrapper(BasePlugin):
    """
    Base class for tool call wrappers (plugins inherit from this).

    Tool wrappers allow intercepting tool execution in the ReAct loop:
    - preprocess: Modify inputs or skip execution entirely
    - postprocess: Modify outputs and/or generate messages
    - on_error: Handle execution errors with custom logic

    Example:
        class CachingToolWrapper(ToolCallWrapper):
            cache: dict = {}

            def preprocess(self, agent, ctx, tool_name, tool_input):
                key = f"{tool_name}:{tool_input.model_dump_json()}"
                if key in self.cache:
                    return ToolSkipResult(output=self.cache[key])
                return tool_input

            def postprocess(self, agent, ctx, tool_name, tool_input, tool_output):
                key = f"{tool_name}:{tool_input.model_dump_json()}"
                self.cache[key] = tool_output
                return ToolCallResult(output=tool_output)
    """

    @abstractmethod
    def preprocess(
        self,
        agent: Agent,
        ctx: ProcessContext,
        tool_name: str,
        tool_input: BaseModel,
    ) -> Union[BaseModel, ToolSkipResult]:
        """
        Preprocess tool input before execution.

        Args:
            agent: The agent instance.
            ctx: The process context.
            tool_name: Name of the tool being called.
            tool_input: Parsed tool arguments as a BaseModel.

        Returns:
            - Return the (possibly modified) tool_input to continue execution
            - Return ToolSkipResult to skip execution and use the provided output
        """
        pass

    @abstractmethod
    def postprocess(
        self,
        agent: Agent,
        ctx: ProcessContext,
        tool_name: str,
        tool_input: BaseModel,
        tool_output: str,
    ) -> ToolCallResult:
        """
        Postprocess tool output after execution.

        This is called after the tool executes (or after preprocess returns
        ToolSkipResult). Use this to modify outputs, log metrics, or emit
        additional messages.

        Args:
            agent: The agent instance.
            ctx: The process context.
            tool_name: Name of the tool that was called.
            tool_input: The tool arguments that were used.
            tool_output: The output from tool execution.

        Returns:
            ToolCallResult with the (possibly modified) output and optional messages.
        """
        pass

    def on_error(
        self,
        agent: Agent,
        ctx: ProcessContext,
        tool_name: str,
        tool_input: BaseModel,
        error: Exception,
    ) -> Optional[str]:
        """
        Handle a tool execution error.

        Override this method to implement custom error handling logic such as
        retries, fallbacks, or error transformation.

        Args:
            agent: The agent instance.
            ctx: The process context.
            tool_name: Name of the tool that failed.
            tool_input: The tool arguments that were used.
            error: The exception that was raised.

        Returns:
            - Return a string to use as the tool output (error is handled)
            - Return None to use default error handling (error message as output)
            - Raise an exception to propagate the error
        """
        return None  # Default: use standard error handling
