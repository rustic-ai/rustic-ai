from abc import ABC, abstractmethod
from functools import cached_property
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, model_validator

from rustic_ai.core.guild.agent_ext.depends.llm.models import ChatCompletionTool
from rustic_ai.core.guild.agent_ext.depends.llm.tools_manager import ToolSpec


class ReActToolset(BaseModel, ABC):
    """
    Abstract base class for tool providers with execution capability.

    A ReActToolset defines both the tools available to the agent (via get_toolspecs)
    and the execution logic for those tools (via execute).

    Subclasses must implement:
    - get_toolspecs(): Return list of ToolSpec objects defining available tools
    - execute(): Execute a tool by name with parsed arguments

    The toolset is fully serializable via the `kind` field which stores the
    fully qualified class name (FQCN) for runtime class resolution.

    Example:
        class CalculatorToolset(ReActToolset):
            def get_toolspecs(self) -> List[ToolSpec]:
                return [
                    ToolSpec(
                        name="calculate",
                        description="Evaluate a math expression",
                        parameter_class=CalculateParams
                    )
                ]

            def execute(self, tool_name: str, args: BaseModel) -> str:
                if tool_name == "calculate":
                    return str(eval(args.expression))
                raise ValueError(f"Unknown tool: {tool_name}")
    """

    kind: Optional[str] = Field(default=None, frozen=True, description="FQCN of the toolset class")

    def model_post_init(self, __context) -> None:
        if not self.kind:
            object.__setattr__(self, "kind", f"{self.__class__.__module__}.{self.__class__.__qualname__}")

    @model_validator(mode="after")
    def _enforce_kind_matches_class(self):
        fqcn = f"{self.__class__.__module__}.{self.__class__.__qualname__}"
        if self.kind and self.kind != fqcn:
            raise ValueError(f"`kind` must be {fqcn!r}, got {self.kind!r}")
        return self

    @abstractmethod
    def get_toolspecs(self) -> List[ToolSpec]:
        """
        Return the list of tool specifications available in this toolset.

        Returns:
            List of ToolSpec objects defining the tools.
        """
        pass

    @abstractmethod
    def execute(self, tool_name: str, args: BaseModel) -> str:
        """
        Execute a tool by name with the given arguments.

        Args:
            tool_name: The name of the tool to execute.
            args: The parsed arguments as a Pydantic model instance.

        Returns:
            The result of the tool execution as a string.

        Raises:
            ValueError: If the tool name is not recognized.
        """
        pass

    @cached_property
    def toolspecs_by_name(self) -> Dict[str, ToolSpec]:
        """Return a dictionary mapping tool names to their specifications."""
        return {spec.name: spec for spec in self.get_toolspecs()}

    def get_toolspec(self, name: str) -> Optional[ToolSpec]:
        """
        Get a tool specification by name.

        Args:
            name: The name of the tool.

        Returns:
            The ToolSpec if found, None otherwise.
        """
        return self.toolspecs_by_name.get(name)

    @cached_property
    def chat_tools(self) -> List[ChatCompletionTool]:
        """
        Convert tool specifications to ChatCompletionTool format for LLM API.

        Returns:
            List of ChatCompletionTool objects.
        """
        return [spec.chat_tool for spec in self.get_toolspecs()]

    @cached_property
    def tool_names(self) -> List[str]:
        """Return list of available tool names."""
        return [spec.name for spec in self.get_toolspecs()]

    @cached_property
    def tool_count(self) -> int:
        """Return the number of tools in this toolset."""
        return len(self.get_toolspecs())


class CompositeToolset(ReActToolset):
    """
    A toolset that combines multiple toolsets into one.

    This allows composing toolsets from different sources while presenting
    them as a single unified toolset to the ReActAgent.

    Example:
        composite = CompositeToolset(
            toolsets=[
                CalculatorToolset(),
                SearchToolset(api_key="...")
            ]
        )
    """

    toolsets: List[ReActToolset] = Field(min_length=1, description="List of toolsets to combine")

    def get_toolspecs(self) -> List[ToolSpec]:
        """Return combined tool specifications from all toolsets."""
        specs = []
        for toolset in self.toolsets:
            specs.extend(toolset.get_toolspecs())
        return specs

    def execute(self, tool_name: str, args: BaseModel) -> str:
        """
        Execute a tool by delegating to the appropriate child toolset.

        Args:
            tool_name: The name of the tool to execute.
            args: The parsed arguments.

        Returns:
            The result of the tool execution.

        Raises:
            ValueError: If the tool name is not found in any child toolset.
        """
        for toolset in self.toolsets:
            if tool_name in toolset.tool_names:
                return toolset.execute(tool_name, args)
        raise ValueError(f"Unknown tool: {tool_name}")
