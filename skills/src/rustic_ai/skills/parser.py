"""Parser for Agent Skills SKILL.md format."""

import logging
import re
from pathlib import Path
from typing import List, Optional, Tuple

import yaml

from .models import (
    SkillAsset,
    SkillDefinition,
    SkillMetadata,
    SkillReference,
    SkillScript,
)

logger = logging.getLogger(__name__)


class SkillParseError(Exception):
    """Raised when a skill cannot be parsed."""

    pass


class SkillParser:
    """
    Parser for Agent Skills format.

    Parses SKILL.md files and discovers associated resources (scripts, references, assets).

    Example SKILL.md format:
        ---
        name: my-skill-name
        description: What this skill does and when to use it
        allowed-tools: Read, Grep, Glob
        model: claude-opus-4-5-20251101
        ---

        # My Skill Name

        [Markdown instructions for the agent]
    """

    SKILL_FILENAME = "SKILL.md"
    SCRIPTS_DIR = "scripts"
    REFERENCES_DIR = "references"
    ASSETS_DIR = "assets"

    # Supported script extensions
    SCRIPT_EXTENSIONS = {".py", ".sh", ".js", ".ts", ".rb", ".bash"}

    @classmethod
    def parse(cls, skill_path: Path) -> SkillDefinition:
        """
        Parse a skill folder into a SkillDefinition.

        Args:
            skill_path: Path to the skill folder containing SKILL.md

        Returns:
            Parsed SkillDefinition

        Raises:
            SkillParseError: If the skill cannot be parsed
        """
        skill_path = Path(skill_path)

        if not skill_path.is_dir():
            raise SkillParseError(f"Skill path is not a directory: {skill_path}")

        skill_file = skill_path / cls.SKILL_FILENAME
        if not skill_file.exists():
            raise SkillParseError(f"SKILL.md not found in {skill_path}")

        # Parse SKILL.md
        content = skill_file.read_text()
        metadata, instructions = cls._parse_skill_md(content, skill_path)

        # Discover resources
        scripts = cls._discover_scripts(skill_path)
        references = cls._discover_references(skill_path)
        assets = cls._discover_assets(skill_path)

        return SkillDefinition(
            metadata=metadata,
            instructions=instructions,
            path=skill_path,
            scripts=scripts,
            references=references,
            assets=assets,
        )

    @classmethod
    def parse_metadata_only(cls, skill_path: Path) -> SkillMetadata:
        """
        Parse only the metadata from a skill (for lazy loading).

        This is faster than full parsing as it only reads the frontmatter.

        Args:
            skill_path: Path to the skill folder

        Returns:
            SkillMetadata from the frontmatter
        """
        skill_path = Path(skill_path)
        skill_file = skill_path / cls.SKILL_FILENAME

        if not skill_file.exists():
            raise SkillParseError(f"SKILL.md not found in {skill_path}")

        content = skill_file.read_text()
        frontmatter, _ = cls._split_frontmatter(content)

        if not frontmatter:
            raise SkillParseError(f"No frontmatter found in {skill_file}")

        return cls._parse_frontmatter(frontmatter, skill_path)

    @classmethod
    def _parse_skill_md(cls, content: str, skill_path: Path) -> Tuple[SkillMetadata, str]:
        """
        Parse SKILL.md content into metadata and instructions.

        Args:
            content: Raw SKILL.md content
            skill_path: Path to skill folder (for error messages)

        Returns:
            Tuple of (SkillMetadata, instructions markdown)
        """
        frontmatter, body = cls._split_frontmatter(content)

        if not frontmatter:
            raise SkillParseError(f"No frontmatter found in SKILL.md at {skill_path}")

        metadata = cls._parse_frontmatter(frontmatter, skill_path)
        instructions = body.strip()

        return metadata, instructions

    @classmethod
    def _split_frontmatter(cls, content: str) -> Tuple[Optional[str], str]:
        """
        Split SKILL.md into frontmatter and body.

        Frontmatter is delimited by --- at the start of the file.

        Args:
            content: Raw file content

        Returns:
            Tuple of (frontmatter YAML string or None, body markdown)
        """
        # Check for frontmatter delimiter at start
        if not content.startswith("---"):
            return None, content

        # Find the closing delimiter
        parts = content.split("---", 2)

        if len(parts) < 3:
            # No closing delimiter found
            return None, content

        frontmatter = parts[1].strip()
        body = parts[2]

        return frontmatter, body

    @classmethod
    def _parse_frontmatter(cls, frontmatter: str, skill_path: Path) -> SkillMetadata:
        """
        Parse YAML frontmatter into SkillMetadata.

        Args:
            frontmatter: YAML string from frontmatter
            skill_path: Path for error messages

        Returns:
            Parsed SkillMetadata
        """
        try:
            data = yaml.safe_load(frontmatter)
        except yaml.YAMLError as e:
            raise SkillParseError(f"Invalid YAML in frontmatter at {skill_path}: {e}")

        if not isinstance(data, dict):
            raise SkillParseError(f"Frontmatter must be a YAML mapping at {skill_path}")

        # Required fields
        if "name" not in data:
            raise SkillParseError(f"Missing required 'name' field in {skill_path}")
        if "description" not in data:
            raise SkillParseError(f"Missing required 'description' field in {skill_path}")

        # Parse allowed-tools (can be string or list)
        allowed_tools = data.get("allowed-tools")
        if isinstance(allowed_tools, str):
            allowed_tools = [t.strip() for t in allowed_tools.split(",")]

        return SkillMetadata(
            name=data["name"],
            description=data["description"],
            allowed_tools=allowed_tools,
            model=data.get("model"),
        )

    @classmethod
    def _discover_scripts(cls, skill_path: Path) -> List[SkillScript]:
        """Discover executable scripts in the skill's scripts/ directory."""
        scripts_dir = skill_path / cls.SCRIPTS_DIR
        if not scripts_dir.exists():
            return []

        scripts = []
        for script_file in scripts_dir.iterdir():
            if script_file.is_file() and script_file.suffix in cls.SCRIPT_EXTENSIONS:
                description = cls._extract_script_description(script_file)
                scripts.append(
                    SkillScript(
                        name=script_file.stem,
                        path=script_file,
                        extension=script_file.suffix,
                        description=description,
                    )
                )

        return scripts

    @classmethod
    def _extract_script_description(cls, script_path: Path) -> Optional[str]:
        """
        Extract description from script docstring or comments.

        Looks for:
        - Python: First docstring
        - Shell/Bash: First comment block starting with #
        """
        try:
            content = script_path.read_text()
        except Exception:
            return None

        ext = script_path.suffix

        if ext == ".py":
            # Look for module docstring
            match = re.match(r'^[\s]*["\']["\']["\'](.+?)["\']["\']["\']', content, re.DOTALL)
            if match:
                return match.group(1).strip().split("\n")[0]

        elif ext in {".sh", ".bash"}:
            # Look for first comment line after shebang
            lines = content.split("\n")
            for line in lines:
                line = line.strip()
                if line.startswith("#!"):
                    continue
                if line.startswith("#"):
                    return line[1:].strip()
                if line:
                    break

        return None

    @classmethod
    def _discover_references(cls, skill_path: Path) -> List[SkillReference]:
        """Discover reference documents in the skill's references/ directory."""
        refs_dir = skill_path / cls.REFERENCES_DIR
        if not refs_dir.exists():
            return []

        references = []
        for ref_file in refs_dir.iterdir():
            if ref_file.is_file():
                references.append(
                    SkillReference(
                        name=ref_file.name,
                        path=ref_file,
                    )
                )

        return references

    @classmethod
    def _discover_assets(cls, skill_path: Path) -> List[SkillAsset]:
        """Discover asset files in the skill's assets/ directory."""
        assets_dir = skill_path / cls.ASSETS_DIR
        if not assets_dir.exists():
            return []

        assets = []
        for asset_file in assets_dir.iterdir():
            if asset_file.is_file():
                assets.append(
                    SkillAsset(
                        name=asset_file.name,
                        path=asset_file,
                    )
                )

        return assets


def parse_skill(skill_path: Path) -> SkillDefinition:
    """
    Convenience function to parse a skill folder.

    Args:
        skill_path: Path to skill folder containing SKILL.md

    Returns:
        Parsed SkillDefinition
    """
    return SkillParser.parse(skill_path)


def parse_skill_metadata(skill_path: Path) -> SkillMetadata:
    """
    Convenience function to parse only skill metadata (lazy loading).

    Args:
        skill_path: Path to skill folder containing SKILL.md

    Returns:
        Parsed SkillMetadata
    """
    return SkillParser.parse_metadata_only(skill_path)
