"""SkillToolset - ReActToolset implementation for Agent Skills.

Bridges Agent Skills with the ReActAgent by converting skill scripts
into executable tools and providing skill instructions.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from rustic_ai.core.guild.agent_ext.depends.llm.tools_manager import ToolSpec
from rustic_ai.llm_agent.react.toolset import ReActToolset

from .executor import ExecutionConfig, ExecutionResult, ScriptExecutor
from .models import SkillDefinition, SkillScript
from .parser import SkillParser

logger = logging.getLogger(__name__)


class ScriptToolParams(BaseModel):
    """Generic parameters for script-based tools."""

    args: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Arguments to pass to the script as a JSON object",
    )
    input_text: Optional[str] = Field(
        default=None,
        description="Text input to pass to the script",
    )


class SkillToolset(ReActToolset):
    """
    A ReActToolset that exposes skill scripts as tools.

    This toolset:
    1. Loads a skill from a directory
    2. Converts each script into a ToolSpec
    3. Executes scripts when tools are called
    4. Provides skill instructions for system prompt injection

    Example usage:
        # Create toolset from skill path
        toolset = SkillToolset.from_path(Path(".claude/skills/pdf"))

        # Use with ReActAgent
        config = ReActAgentConfig(
            model="gpt-4",
            toolset=toolset,
            system_prompt=toolset.get_system_prompt_addition(),
        )

        # Or compose with other toolsets
        composite = CompositeToolset(
            toolsets=[toolset, CalculatorToolset()]
        )
    """

    # Skill definition (loaded from path)
    skill: SkillDefinition = Field(description="The loaded skill definition")

    # Execution configuration
    execution_config: ExecutionConfig = Field(
        default_factory=ExecutionConfig,
        description="Configuration for script execution",
    )

    # Prefix for tool names to avoid conflicts
    tool_prefix: str = Field(
        default="",
        description="Prefix to add to tool names (e.g., 'pdf_' for pdf skill)",
    )

    def get_toolspecs(self) -> List[ToolSpec]:
        """
        Convert skill scripts into ToolSpecs.

        Each script becomes a tool that the ReActAgent can call.
        The tool description comes from the script's docstring or filename.
        """
        specs = []

        for script in self.skill.scripts:
            tool_name = f"{self.tool_prefix}{script.name}" if self.tool_prefix else script.name

            # Build description from script info
            description = script.description or f"Execute the {script.name} script from {self.skill.name} skill"

            specs.append(
                ToolSpec(
                    name=tool_name,
                    description=description,
                    parameter_class=ScriptToolParams,
                )
            )

        return specs

    def execute(self, tool_name: str, args: BaseModel) -> str:
        """
        Execute a skill script as a tool.

        Args:
            tool_name: Name of the tool (script name with optional prefix)
            args: ScriptToolParams with arguments

        Returns:
            Script output as string

        Raises:
            ValueError: If tool name not found
        """
        # Remove prefix if present
        script_name = tool_name
        if self.tool_prefix and tool_name.startswith(self.tool_prefix):
            script_name = tool_name[len(self.tool_prefix) :]

        # Find the script
        script = self.skill.get_script(script_name)
        if not script:
            raise ValueError(f"Unknown tool: {tool_name}")

        # Parse arguments
        if isinstance(args, ScriptToolParams):
            script_args = args.args or {}
            if args.input_text:
                script_args["input_text"] = args.input_text
        elif isinstance(args, dict):
            script_args = args
        else:
            script_args = args.model_dump() if hasattr(args, "model_dump") else {}

        # Execute script
        executor = ScriptExecutor(self.execution_config)
        result: ExecutionResult = executor.execute(script, script_args)

        if result.success:
            return result.output.strip() if result.output else "Script executed successfully (no output)"
        else:
            error_msg = result.error or "Unknown error"
            return f"Script execution failed: {error_msg}"

    def get_system_prompt_addition(self) -> str:
        """
        Get the skill instructions to add to the system prompt.

        This includes:
        - Skill name and description
        - Full markdown instructions from SKILL.md
        - Available scripts and their descriptions
        - Reference documents (if any)

        Returns:
            Formatted string to append to system prompt
        """
        lines = [
            f"## Skill: {self.skill.name}",
            "",
            self.skill.instructions,
            "",
        ]

        # Add script documentation
        if self.skill.scripts:
            lines.extend(
                [
                    "### Available Scripts",
                    "",
                ]
            )
            for script in self.skill.scripts:
                prefix = f"{self.tool_prefix}" if self.tool_prefix else ""
                desc = script.description or "No description"
                lines.append(f"- **{prefix}{script.name}**: {desc}")
            lines.append("")

        # Add reference documents
        if self.skill.references:
            lines.extend(
                [
                    "### Reference Documents",
                    "",
                ]
            )
            for ref in self.skill.references:
                lines.append(f"- {ref.name}")
            lines.append("")

        return "\n".join(lines)

    def load_reference(self, name: str) -> Optional[str]:
        """
        Load a reference document by name.

        Args:
            name: Reference filename

        Returns:
            Reference content or None if not found
        """
        ref = self.skill.get_reference(name)
        if ref:
            return ref.load()
        return None

    def get_asset_path(self, name: str) -> Optional[Path]:
        """
        Get the path to an asset file.

        Args:
            name: Asset filename

        Returns:
            Path to asset or None if not found
        """
        asset = self.skill.get_asset(name)
        if asset:
            return asset.path
        return None

    @classmethod
    def from_path(
        cls,
        skill_path: Path,
        tool_prefix: Optional[str] = None,
        execution_config: Optional[ExecutionConfig] = None,
    ) -> "SkillToolset":
        """
        Create a SkillToolset from a skill directory.

        Args:
            skill_path: Path to skill folder containing SKILL.md
            tool_prefix: Optional prefix for tool names
            execution_config: Optional execution configuration

        Returns:
            Configured SkillToolset
        """
        skill = SkillParser.parse(skill_path)

        # Auto-generate prefix from skill name if not provided
        prefix = tool_prefix if tool_prefix is not None else f"{skill.name.replace('-', '_')}_"

        return cls(
            skill=skill,
            tool_prefix=prefix,
            execution_config=execution_config or ExecutionConfig(),
        )


class MultiSkillToolset(ReActToolset):
    """
    A toolset that combines multiple skills into one.

    This is useful when you want to enable multiple skills for an agent
    without manually composing them.

    Example:
        toolset = MultiSkillToolset.from_paths([
            Path(".claude/skills/pdf"),
            Path(".claude/skills/csv"),
            Path(".claude/skills/web-search"),
        ])
    """

    skill_toolsets: List[SkillToolset] = Field(
        min_length=1,
        description="List of skill toolsets",
    )

    def get_toolspecs(self) -> List[ToolSpec]:
        """Return combined tool specs from all skill toolsets."""
        specs = []
        for toolset in self.skill_toolsets:
            specs.extend(toolset.get_toolspecs())
        return specs

    def execute(self, tool_name: str, args: BaseModel) -> str:
        """
        Execute a tool by delegating to the appropriate skill toolset.

        Args:
            tool_name: The name of the tool to execute
            args: The parsed arguments

        Returns:
            The result of tool execution

        Raises:
            ValueError: If tool not found in any skill
        """
        for toolset in self.skill_toolsets:
            if tool_name in toolset.tool_names:
                return toolset.execute(tool_name, args)
        raise ValueError(f"Unknown tool: {tool_name}")

    def get_combined_system_prompt(self) -> str:
        """
        Get combined system prompt additions from all skills.

        Returns:
            Combined formatted string for system prompt
        """
        sections = []
        for toolset in self.skill_toolsets:
            sections.append(toolset.get_system_prompt_addition())
        return "\n---\n".join(sections)

    @classmethod
    def from_paths(
        cls,
        skill_paths: List[Path],
        execution_config: Optional[ExecutionConfig] = None,
    ) -> "MultiSkillToolset":
        """
        Create a MultiSkillToolset from multiple skill directories.

        Args:
            skill_paths: List of paths to skill folders
            execution_config: Optional shared execution config

        Returns:
            Configured MultiSkillToolset
        """
        toolsets = []
        for path in skill_paths:
            toolsets.append(
                SkillToolset.from_path(
                    path,
                    execution_config=execution_config,
                )
            )
        return cls(skill_toolsets=toolsets)


def create_skill_toolset(
    skill_path: Path,
    tool_prefix: Optional[str] = None,
    timeout_seconds: int = 30,
) -> SkillToolset:
    """
    Convenience function to create a SkillToolset.

    Args:
        skill_path: Path to skill folder
        tool_prefix: Optional prefix for tool names
        timeout_seconds: Script execution timeout

    Returns:
        Configured SkillToolset
    """
    config = ExecutionConfig(timeout_seconds=timeout_seconds)
    return SkillToolset.from_path(skill_path, tool_prefix, config)
