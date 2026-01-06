"""Models for Agent Skills support."""

from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SkillMetadata(BaseModel):
    """
    Metadata extracted from SKILL.md frontmatter.

    This is the lightweight representation loaded during discovery,
    containing only the information needed for semantic matching.
    """

    name: str = Field(description="Unique identifier for the skill (lowercase, hyphens)")
    description: str = Field(description="What the skill does and when to use it (max 1024 chars)")
    allowed_tools: Optional[List[str]] = Field(
        default=None,
        description="Tools the agent can use without permission when skill is active",
    )
    model: Optional[str] = Field(
        default=None,
        description="Specific model to use when skill is active",
    )


class SkillScript(BaseModel):
    """Represents an executable script in a skill."""

    name: str = Field(description="Script filename without extension")
    path: Path = Field(description="Full path to the script")
    extension: str = Field(description="File extension (py, sh, etc.)")
    description: Optional[str] = Field(
        default=None,
        description="Description extracted from script docstring or comments",
    )

    @property
    def interpreter(self) -> str:
        """Return the interpreter for this script type."""
        interpreters = {
            ".py": "python",
            ".sh": "bash",
            ".js": "node",
            ".ts": "npx ts-node",
            ".rb": "ruby",
        }
        return interpreters.get(self.extension, "bash")


class SkillReference(BaseModel):
    """Represents a reference document in a skill."""

    name: str = Field(description="Reference filename")
    path: Path = Field(description="Full path to the reference file")
    content: Optional[str] = Field(
        default=None,
        description="Content of the reference (loaded on demand)",
    )

    def load(self) -> str:
        """Load the reference content from disk."""
        if self.content is None:
            self.content = self.path.read_text()
        return self.content


class SkillAsset(BaseModel):
    """Represents an asset file in a skill (templates, configs, etc.)."""

    name: str = Field(description="Asset filename")
    path: Path = Field(description="Full path to the asset")


class SkillDefinition(BaseModel):
    """
    Full skill definition parsed from a skill folder.

    Contains metadata, instructions, scripts, references, and assets.
    """

    # Metadata from frontmatter
    metadata: SkillMetadata

    # Markdown instructions (body of SKILL.md)
    instructions: str = Field(description="Markdown instructions for the agent")

    # Skill location
    path: Path = Field(description="Path to the skill folder")

    # Optional components
    scripts: List[SkillScript] = Field(default_factory=list, description="Executable scripts")
    references: List[SkillReference] = Field(default_factory=list, description="Reference documents")
    assets: List[SkillAsset] = Field(default_factory=list, description="Asset files")

    @property
    def name(self) -> str:
        """Convenience accessor for skill name."""
        return self.metadata.name

    @property
    def description(self) -> str:
        """Convenience accessor for skill description."""
        return self.metadata.description

    def get_script(self, name: str) -> Optional[SkillScript]:
        """Get a script by name."""
        for script in self.scripts:
            if script.name == name:
                return script
        return None

    def get_reference(self, name: str) -> Optional[SkillReference]:
        """Get a reference by name."""
        for ref in self.references:
            if ref.name == name:
                return ref
        return None

    def get_asset(self, name: str) -> Optional[SkillAsset]:
        """Get an asset by name."""
        for asset in self.assets:
            if asset.name == name:
                return asset
        return None


class SkillSource(BaseModel):
    """Represents a source for skills (GitHub repo, local path, etc.)."""

    name: str = Field(description="Source identifier")
    type: str = Field(description="Source type: github, local, url")
    location: str = Field(description="GitHub repo (owner/repo), local path, or URL")
    branch: str = Field(default="main", description="Git branch for GitHub sources")
    skills_path: str = Field(default="skills", description="Path to skills folder within source")


class SkillRegistry(BaseModel):
    """Registry of available skills from various sources."""

    sources: Dict[str, SkillSource] = Field(default_factory=dict)
    skills: Dict[str, SkillMetadata] = Field(default_factory=dict)
    skill_locations: Dict[str, Path] = Field(default_factory=dict)

    def add_source(self, source: SkillSource):
        """Add a skill source to the registry."""
        self.sources[source.name] = source

    def register_skill(self, metadata: SkillMetadata, path: Path):
        """Register a discovered skill."""
        self.skills[metadata.name] = metadata
        self.skill_locations[metadata.name] = path

    def get_skill_path(self, name: str) -> Optional[Path]:
        """Get the path to a registered skill."""
        return self.skill_locations.get(name)

    def list_skills(self) -> List[SkillMetadata]:
        """List all registered skills."""
        return list(self.skills.values())

    def search(self, query: str) -> List[SkillMetadata]:
        """
        Simple keyword search over skill names and descriptions.

        For more sophisticated matching, consider using embeddings.
        """
        query_lower = query.lower()
        results = []
        for skill in self.skills.values():
            if query_lower in skill.name.lower() or query_lower in skill.description.lower():
                results.append(skill)
        return results
