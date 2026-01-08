"""SkillToolset - ReActToolset implementation for Agent Skills.

Bridges Agent Skills with the ReActAgent by converting skill scripts
into executable tools and providing skill instructions.
"""

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Union

from pydantic import BaseModel, Field, model_validator

from rustic_ai.core.guild.agent_ext.depends.llm.tools_manager import ToolSpec
from rustic_ai.llm_agent.react.toolset import ReActToolset

from .executor import ExecutionConfig, ExecutionResult, ScriptExecutor
from .models import SkillDefinition, SkillScript
from .parser import SkillParser


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
    A unified ReActToolset that exposes one or more skill scripts as tools.

    This toolset:
    1. Loads skills from directories (one or multiple)
    2. Converts each script into a ToolSpec
    3. Executes scripts when tools are called
    4. Provides skill instructions for system prompt injection

    Example usage:
        # Create toolset from a single skill path
        toolset = SkillToolset.from_path(Path("/tmp/rustic-skills/pdf"))

        # Create toolset from multiple skill paths
        toolset = SkillToolset.from_paths([
            Path("/tmp/rustic-skills/pdf"),
            Path("/tmp/rustic-skills/csv"),
        ])

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

    The toolset supports path-based serialization for YAML/JSON specs:

        # In agent spec YAML (single skill):
        properties:
          toolset:
            kind: rustic_ai.skills.toolset.SkillToolset
            skill_paths:
              - "/path/to/skill"

        # In agent spec YAML (multiple skills):
        properties:
          toolset:
            kind: rustic_ai.skills.toolset.SkillToolset
            skill_paths:
              - "/path/to/skill1"
              - "/path/to/skill2"

        # At runtime, skills are loaded from skill_paths
    """

    # Paths to skill directories (for lazy loading from specs)
    skill_paths: List[str] = Field(
        default_factory=list,
        description="List of paths to skill directories. Used for spec serialization.",
    )

    # Skill definitions (loaded from paths or provided directly)
    skills: List[SkillDefinition] = Field(
        default_factory=list,
        description="The loaded skill definitions",
    )

    # Execution configuration
    execution_config: ExecutionConfig = Field(
        default_factory=ExecutionConfig,
        description="Configuration for script execution",
    )

    # Prefix for tool names (only used for single-skill case)
    # For multi-skill, each skill gets its own prefix from its name
    tool_prefix: Optional[str] = Field(
        default=None,
        description="Prefix to add to tool names (e.g., 'pdf_' for pdf skill). "
        "If None, auto-generated from skill name.",
    )

    @staticmethod
    def _default_tool_prefix(skill: SkillDefinition) -> str:
        return f"{skill.name.replace('-', '_')}_"

    @staticmethod
    def _normalize_skill_paths(skill_paths: Iterable[Union[Path, str]]) -> List[Path]:
        return [Path(path) for path in skill_paths]

    @classmethod
    def _parse_skills_from_paths(cls, skill_paths: Iterable[Union[Path, str]]) -> List[SkillDefinition]:
        skills = []
        for path in cls._normalize_skill_paths(skill_paths):
            if not path.exists():
                raise ValueError(f"Skill path does not exist: {path}")
            skills.append(SkillParser.parse(path))
        return skills

    @staticmethod
    def _serialize_skill_paths(skill_paths: Iterable[Union[Path, str]]) -> List[str]:
        return [str(Path(path).absolute()) for path in skill_paths]

    def _ensure_skill_configuration(self) -> None:
        if not self.skills:
            raise ValueError("Either 'skills' or 'skill_paths' must be provided")

        if len(self.skills) == 1 and self.tool_prefix is None:
            object.__setattr__(self, "tool_prefix", self._default_tool_prefix(self.skills[0]))

    @model_validator(mode="after")
    def _load_skills_from_paths(self):
        """Load skills from skill_paths if skills are not directly provided."""
        if not self.skills and self.skill_paths:
            loaded_skills = self._parse_skills_from_paths(self.skill_paths)
            object.__setattr__(self, "skills", loaded_skills)

        self._ensure_skill_configuration()

        return self

    def _get_tool_prefix(self, skill: SkillDefinition) -> str:
        """Get the tool prefix for a skill."""
        # For single skill, use the explicitly set prefix
        if len(self.skills) == 1 and self.tool_prefix is not None:
            return self.tool_prefix
        # For multiple skills or no explicit prefix, derive from skill name
        return self._default_tool_prefix(skill)

    def model_dump(self, **kwargs) -> Dict[str, Any]:
        """
        Override model_dump to prefer skill_paths for serialization.

        When skill_paths are available, serialize with them instead of the full
        skill definitions. This makes specs portable across environments.
        """
        data = super().model_dump(**kwargs)

        if self.skill_paths:
            serialized = dict(data)
            serialized["skill_paths"] = list(self.skill_paths)
            serialized.pop("skills", None)
            return serialized

        return data

    def get_toolspecs(self) -> List[ToolSpec]:
        """
        Convert skill scripts into ToolSpecs.

        Each script becomes a tool that the ReActAgent can call.
        The tool description comes from the script's docstring or filename.
        """
        specs = []

        for skill in self.skills:
            prefix = self._get_tool_prefix(skill)
            for script in skill.scripts:
                tool_name = f"{prefix}{script.name}" if prefix else script.name

                # Build description from script info
                description = script.description or f"Execute the {script.name} script from {skill.name} skill"

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
            tool_name: Name of the tool (script name with prefix)
            args: ScriptToolParams with arguments

        Returns:
            Script output as string

        Raises:
            ValueError: If tool name not found
        """
        # Find the skill and script for this tool
        for skill in self.skills:
            prefix = self._get_tool_prefix(skill)
            if tool_name.startswith(prefix):
                script_name = tool_name[len(prefix) :] if prefix else tool_name
                script = skill.get_script(script_name)
                if script:
                    return self._execute_script(script, args)

        # Also try matching without prefix for backward compatibility
        if len(self.skills) == 1:
            script = self.skills[0].get_script(tool_name)
            if script:
                return self._execute_script(script, args)

        raise ValueError(f"Unknown tool: {tool_name}")

    def _execute_script(self, script: SkillScript, args: BaseModel) -> str:
        """Execute a script and return the result."""
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

        This includes all skills' instructions combined.

        Returns:
            Formatted string to append to system prompt
        """
        sections = []
        for skill in self.skills:
            sections.append(self._format_skill_prompt(skill))
        return "\n---\n".join(sections)

    def _format_skill_prompt(self, skill: SkillDefinition) -> str:
        """Format system prompt section for a single skill."""
        prefix = self._get_tool_prefix(skill)

        lines = [
            f"## Skill: {skill.name}",
            "",
            skill.instructions,
            "",
        ]

        # Add script documentation
        if skill.scripts:
            lines.extend(
                [
                    "### Available Scripts",
                    "",
                ]
            )
            for script in skill.scripts:
                desc = script.description or "No description"
                lines.append(f"- **{prefix}{script.name}**: {desc}")
            lines.append("")

        # Add reference documents
        if skill.references:
            lines.extend(
                [
                    "### Reference Documents",
                    "",
                ]
            )
            for ref in skill.references:
                lines.append(f"- {ref.name}")
            lines.append("")

        return "\n".join(lines)

    def get_combined_system_prompt(self) -> str:
        """Alias for get_system_prompt_addition (for multi-skill compatibility)."""
        return self.get_system_prompt_addition()

    def load_reference(self, name: str) -> Optional[str]:
        """
        Load a reference document by name from any skill.

        Args:
            name: Reference filename

        Returns:
            Reference content or None if not found
        """
        for skill in self.skills:
            ref = skill.get_reference(name)
            if ref:
                return ref.load()
        return None

    def get_asset_path(self, name: str) -> Optional[Path]:
        """
        Get the path to an asset file from any skill.

        Args:
            name: Asset filename

        Returns:
            Path to asset or None if not found
        """
        for skill in self.skills:
            asset = skill.get_asset(name)
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
        Create a SkillToolset from a single skill directory.

        Args:
            skill_path: Path to skill folder containing SKILL.md
            tool_prefix: Optional prefix for tool names
            execution_config: Optional execution configuration

        Returns:
            Configured SkillToolset
        """
        skills = cls._parse_skills_from_paths([skill_path])

        return cls(
            skill_paths=cls._serialize_skill_paths([skill_path]),
            skills=skills,
            tool_prefix=tool_prefix,
            execution_config=execution_config or ExecutionConfig(),
        )

    @classmethod
    def from_paths(
        cls,
        skill_paths: List[Path],
        execution_config: Optional[ExecutionConfig] = None,
    ) -> "SkillToolset":
        """
        Create a SkillToolset from multiple skill directories.

        Args:
            skill_paths: List of paths to skill folders
            execution_config: Optional shared execution config

        Returns:
            Configured SkillToolset
        """
        config = execution_config or ExecutionConfig()
        skills = cls._parse_skills_from_paths(skill_paths)

        return cls(
            skill_paths=cls._serialize_skill_paths(skill_paths),
            skills=skills,
            execution_config=config,
        )


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


class MarketplaceSkillToolset(ReActToolset):
    """
    A SkillToolset that auto-installs skills from a marketplace source.

    This toolset lazily downloads and installs skills from remote sources
    (like GitHub) on first use, making agent specs portable without
    embedding absolute paths.

    Example usage:
        # In code (single skill)
        toolset = MarketplaceSkillToolset(
            source="anthropic",
            skill_names=["pdf"],
        )

        # In code (multiple skills)
        toolset = MarketplaceSkillToolset(
            source="anthropic",
            skill_names=["pdf", "xlsx"],
        )

        # In YAML spec
        properties:
          toolset:
            kind: rustic_ai.skills.toolset.MarketplaceSkillToolset
            source: anthropic
            skill_names:
              - pdf
              - xlsx

    The skills will be downloaded and installed automatically when
    the toolset is first used (during validation or tool execution).
    """

    # Marketplace source name (e.g., "anthropic")
    source: str = Field(
        default="anthropic",
        description="Marketplace source name (e.g., 'anthropic' for anthropics/skills)",
    )

    # Names of the skills to install (e.g., ["pdf", "xlsx"])
    skill_names: List[str] = Field(
        description="Names of skills to install from the marketplace",
    )

    # Optional installation path (uses default if not specified)
    install_path: Optional[str] = Field(
        default=None,
        description="Custom installation path for skills",
    )

    # Optional cache path for downloaded repos
    cache_path: Optional[str] = Field(
        default=None,
        description="Custom cache path for marketplace downloads",
    )

    # Force reinstall even if already installed
    force: bool = Field(
        default=False,
        description="Force reinstall even if skill is already installed",
    )

    # Execution configuration
    execution_config: ExecutionConfig = Field(
        default_factory=ExecutionConfig,
        description="Configuration for script execution",
    )

    # Tool name prefix (only used for single skill, auto-generated otherwise)
    tool_prefix: Optional[str] = Field(
        default=None,
        description="Prefix for tool names (only for single skill)",
    )

    # Internal: The underlying SkillToolset (populated after installation)
    _inner_toolset: Optional[SkillToolset] = None

    # Internal: Paths where skills were installed
    _installed_paths: List[str] = []

    @model_validator(mode="after")
    def _install_and_load(self):
        """Install skills from marketplace and create inner toolset."""
        if self._inner_toolset is None:
            # Import here to avoid circular imports
            from .marketplace import SkillMarketplace

            # Configure marketplace
            marketplace_kwargs = {}
            if self.install_path:
                marketplace_kwargs["install_path"] = Path(self.install_path)
            if self.cache_path:
                marketplace_kwargs["cache_path"] = Path(self.cache_path)

            marketplace = SkillMarketplace(**marketplace_kwargs)

            # Install each skill
            installed_paths = []
            for skill_name in self.skill_names:
                try:
                    installed_path = marketplace.install(skill_name, force=self.force)
                    installed_paths.append(installed_path)
                except Exception as e:
                    raise ValueError(f"Failed to install skill '{skill_name}': {e}")

            # Create inner toolset from installed paths
            if len(installed_paths) == 1:
                inner = SkillToolset.from_path(
                    installed_paths[0],
                    tool_prefix=self.tool_prefix,
                    execution_config=self.execution_config,
                )
            else:
                inner = SkillToolset.from_paths(
                    installed_paths,
                    execution_config=self.execution_config,
                )

            object.__setattr__(self, "_inner_toolset", inner)
            object.__setattr__(self, "_installed_paths", [str(p) for p in installed_paths])

        return self

    def model_dump(self, **kwargs) -> Dict[str, Any]:
        """
        Serialize to dict, keeping only marketplace reference (not local paths).
        """
        data = {
            "source": self.source,
            "skill_names": self.skill_names,
            "execution_config": self.execution_config.model_dump(),
        }

        if self.tool_prefix:
            data["tool_prefix"] = self.tool_prefix
        if self.install_path:
            data["install_path"] = self.install_path
        if self.cache_path:
            data["cache_path"] = self.cache_path

        return data

    def _require_inner_toolset(self) -> SkillToolset:
        """Return the inner toolset or raise if missing."""
        if self._inner_toolset is None:
            raise ValueError("Inner toolset not initialized")
        return self._inner_toolset

    def _delegate(self, method_name: str, *args, **kwargs):
        inner = self._require_inner_toolset()
        return getattr(inner, method_name)(*args, **kwargs)

    def get_toolspecs(self) -> List[ToolSpec]:
        """Return tool specs from the inner toolset."""
        return self._delegate("get_toolspecs")

    def execute(self, tool_name: str, args: BaseModel) -> str:
        """Execute a tool via the inner toolset."""
        return self._delegate("execute", tool_name, args)

    def get_system_prompt_addition(self) -> str:
        """Get system prompt addition from inner toolset."""
        return self._delegate("get_system_prompt_addition")

    # Alias for multi-skill compatibility
    def get_combined_system_prompt(self) -> str:
        """Alias for get_system_prompt_addition."""
        return self.get_system_prompt_addition()

    @property
    def installed_paths(self) -> List[str]:
        """Paths where skills were installed."""
        return self._installed_paths

    @classmethod
    def from_marketplace(
        cls,
        skill_names: Union[str, List[str]],
        source: str = "anthropic",
        execution_config: Optional[ExecutionConfig] = None,
        tool_prefix: Optional[str] = None,
        force: bool = False,
    ) -> "MarketplaceSkillToolset":
        """
        Create a MarketplaceSkillToolset for one or more skills.

        Args:
            skill_names: Name or list of names of skills (e.g., "pdf" or ["pdf", "xlsx"])
            source: Marketplace source (default: "anthropic")
            execution_config: Optional execution configuration
            tool_prefix: Optional tool name prefix (only for single skill)
            force: Force reinstall even if skill is already installed

        Returns:
            Configured MarketplaceSkillToolset
        """
        if isinstance(skill_names, str):
            skill_names = [skill_names]

        return cls(
            source=source,
            skill_names=skill_names,
            execution_config=execution_config or ExecutionConfig(),
            tool_prefix=tool_prefix,
            force=force,
        )
